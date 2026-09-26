#include "clang/AST/ASTConsumer.h"
#include "clang/AST/DeclCXX.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/FrontendAction.h"
#include "clang/Frontend/FrontendPluginRegistry.h"
#include "clang/Basic/Version.h"
#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/DenseSet.h"
#include "llvm/Support/FormatVariadic.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"

#include <string>
#include <vector>
#include <cctype>

using namespace clang;

namespace {

template <class T> std::string pointerID(const T *Pointer) {
  std::string Formatted =
      llvm::formatv("{0:p}", static_cast<const void *>(Pointer)).str();
  // Clang's JSONNodeDumper emits the same pointer without fixed-width zero
  // padding and with lower-case hexadecimal digits.
  const std::size_t FirstDigit = Formatted.find_first_not_of('0', 2);
  std::string Canonical =
      "0x" + (FirstDigit == std::string::npos ? std::string("0")
                                               : Formatted.substr(FirstDigit));
  for (char &Character : Canonical)
    Character = static_cast<char>(
        std::tolower(static_cast<unsigned char>(Character)));
  return Canonical;
}

const char *captureKindName(LambdaCaptureKind Kind) {
  switch (Kind) {
  case LCK_This:
    return "this_by_reference";
  case LCK_StarThis:
    return "this_by_copy";
  case LCK_ByCopy:
    return "by_copy";
  case LCK_ByRef:
    return "by_reference";
  case LCK_VLAType:
    return "vla_type";
  }
  return "unknown";
}

class CaptureVisitor : public RecursiveASTVisitor<CaptureVisitor> {
public:
  bool TraverseCompoundStmt(CompoundStmt *Statement) {
    if (!Statement)
      return true;
    // Bind only declarations directly in this lexical compound statement.
    // A nearest-enclosing-compound heuristic would misclassify for/if initializers.
    for (const Stmt *Child : Statement->body()) {
      if (const auto *Declarations = dyn_cast_or_null<DeclStmt>(Child))
        for (const Decl *Declaration : Declarations->decls())
          if (const auto *Variable = dyn_cast<VarDecl>(Declaration))
            DirectDeclarationScopes[Variable] = Statement;
    }
    return RecursiveASTVisitor<CaptureVisitor>::TraverseCompoundStmt(Statement);
  }

  bool VisitVarDecl(VarDecl *Variable) {
    if (!Variable || !Variable->isLocalVarDecl() ||
        Variable->getType()->isDependentType() ||
        !SeenLocalVariables.insert(Variable).second)
      return true;
    const CXXRecordDecl *Record = Variable->getType()->getAsCXXRecordDecl();
    if (!Record || !Record->hasDefinition())
      return true; // References, pointers, arrays and dependent types are not covered.
    Record = Record->getDefinition();
    const CXXDestructorDecl *Destructor = Record->getDestructor();
    const CompoundStmt *Scope = DirectDeclarationScopes.lookup(Variable);
    const bool Automatic = Variable->getStorageDuration() == SD_Automatic;
    llvm::json::Object Item;
    Item["variable_declaration_id"] = pointerID(Variable);
    Item["declaring_compound_statement_id"] =
        Scope ? llvm::json::Value(pointerID(Scope)) : llvm::json::Value(nullptr);
    Item["record_declaration_id"] = pointerID(Record);
    Item["destructor_declaration_id"] = Destructor
        ? llvm::json::Value(pointerID(Destructor)) : llvm::json::Value(nullptr);
    Item["has_automatic_storage_duration"] = Automatic;
    Item["has_nontrivial_destructor"] = Record->hasNonTrivialDestructor();
    const char *Reason = !Automatic ? "non_automatic_storage_duration"
        : !Scope ? "not_direct_compound_declaration" : nullptr;
    Item["support_status"] = Reason ? "unsupported" : "observed";
    Item["unsupported_reason"] = Reason
        ? llvm::json::Value(Reason) : llvm::json::Value(nullptr);
    LocalRecordObjects.push_back(std::move(Item));
    return true;
  }

  bool VisitExprWithCleanups(ExprWithCleanups *Expression) {
    if (!Expression || !SeenExpressionCleanups.insert(Expression).second)
      return true;
    llvm::json::Object Item;
    Item["expression_id"] = pointerID(Expression);
    Item["subexpression_id"] = pointerID(Expression->getSubExpr());
    Item["num_objects"] =
        static_cast<int64_t>(Expression->getNumObjects());
    Item["cleanups_have_side_effects"] =
        Expression->cleanupsHaveSideEffects();
    ExpressionCleanups.push_back(std::move(Item));
    return true;
  }

  bool TraverseLambdaExpr(LambdaExpr *Expression) {
    if (!Expression)
      return true;
    if (!SeenLambdas.insert(Expression).second)
      return true;

    CXXRecordDecl *Closure = Expression->getLambdaClass();
    llvm::DenseMap<const ValueDecl *, FieldDecl *> CaptureFields;
    FieldDecl *ThisCapture = nullptr;
    Closure->getCaptureFields(CaptureFields, ThisCapture);

    auto Init = Expression->capture_init_begin();
    const bool CaptureInitializerCountMismatch =
        Expression->capture_size() != Closure->capture_size();
    unsigned Index = 0;
    for (const LambdaCapture &Capture : Expression->captures()) {
      const Expr *Initializer =
          Index < Expression->capture_size() ? Init[Index] : nullptr;
      const ValueDecl *CapturedDeclaration =
          Capture.capturesVariable() ? Capture.getCapturedVar() : nullptr;
      const auto *CapturedVariable = dyn_cast_or_null<VarDecl>(CapturedDeclaration);
      const bool IsInitCapture =
          CapturedVariable && CapturedVariable->isInitCapture();
      const bool IsThisCapture = Capture.capturesThis();
      const bool IsVLACapture = Capture.capturesVLAType();

      const FieldDecl *Field = nullptr;
      if (IsThisCapture)
        Field = ThisCapture;
      else if (CapturedDeclaration && !IsInitCapture) {
        auto Found = CaptureFields.find(CapturedDeclaration);
        if (Found != CaptureFields.end())
          Field = Found->second;
      }

      const char *UnsupportedReason = nullptr;
      if (CaptureInitializerCountMismatch)
        UnsupportedReason = "capture_initializer_count_mismatch";
      else if (IsInitCapture)
        UnsupportedReason = "init_capture_not_mapped_by_getCaptureFields";
      else if (IsThisCapture)
        UnsupportedReason = "this_capture_not_supported";
      else if (IsVLACapture)
        UnsupportedReason = "vla_type_capture_not_supported";
      else if (!CapturedDeclaration)
        UnsupportedReason = "capture_has_no_value_declaration";
      else if (!Field)
        UnsupportedReason = "capture_field_mapping_missing";

      llvm::json::Object Item;
      llvm::json::Array Enclosing;
      for (const LambdaExpr *Outer : LambdaStack)
        Enclosing.push_back(pointerID(Outer));
      Item["lambda_id"] = pointerID(Expression);
      Item["closure_declaration_id"] = pointerID(Closure);
      Item["enclosing_lambda_ids"] = llvm::json::Value(std::move(Enclosing));
      Item["capture_index"] = static_cast<int64_t>(Index);
      Item["capture_kind"] = captureKindName(Capture.getCaptureKind());
      Item["is_implicit"] = Capture.isImplicit();
      Item["is_init_capture"] = IsInitCapture;
      Item["is_this_capture"] = IsThisCapture;
      Item["is_vla_type_capture"] = IsVLACapture;
      Item["captured_declaration_id"] =
          CapturedDeclaration
              ? llvm::json::Value(pointerID(CapturedDeclaration))
              : llvm::json::Value(nullptr);
      Item["field_declaration_id"] =
          Field ? llvm::json::Value(pointerID(Field))
                : llvm::json::Value(nullptr);
      Item["initializer_expression_id"] =
          Initializer ? llvm::json::Value(pointerID(Initializer))
                      : llvm::json::Value(nullptr);
      Item["support_status"] = UnsupportedReason ? "unsupported" : "observed";
      Item["unsupported_reason"] =
          UnsupportedReason ? llvm::json::Value(UnsupportedReason)
                            : llvm::json::Value(nullptr);
      Captures.push_back(std::move(Item));
      ++Index;
    }

    // Capture initializers are evaluated outside the newly-created closure.
    // A lambda within one therefore has the same enclosing-lambda path as
    // this LambdaExpr, rather than this LambdaExpr itself as an ancestor.
    for (const Expr *Initializer : Expression->capture_inits())
      if (!TraverseStmt(const_cast<Expr *>(Initializer)))
        return false;

    LambdaStack.push_back(Expression);
    const bool Result = TraverseStmt(Expression->getBody());
    LambdaStack.pop_back();
    return Result;
  }

  llvm::json::Array takeCaptures() { return std::move(Captures); }
  llvm::json::Array takeExpressionCleanups() {
    return std::move(ExpressionCleanups);
  }
  llvm::json::Array takeLocalRecordObjects() {
    return std::move(LocalRecordObjects);
  }

private:
  std::vector<const LambdaExpr *> LambdaStack;
  llvm::DenseSet<const LambdaExpr *> SeenLambdas;
  llvm::DenseSet<const ExprWithCleanups *> SeenExpressionCleanups;
  llvm::DenseSet<const VarDecl *> SeenLocalVariables;
  llvm::DenseMap<const VarDecl *, const CompoundStmt *> DirectDeclarationScopes;
  llvm::json::Array Captures;
  llvm::json::Array ExpressionCleanups;
  llvm::json::Array LocalRecordObjects;
};

class CaptureConsumer : public ASTConsumer {
public:
  void HandleTranslationUnit(ASTContext &Context) override {
    CaptureVisitor Visitor;
    Visitor.TraverseDecl(Context.getTranslationUnitDecl());

    llvm::outs() << "{\"schema_version\":\"clang-native-captures/v1\","
                    "\"capture_coverage\":\"visited_lambda_initializers_and_"
                    "bodies_not_exhaustive\","
                    "\"cleanup_coverage\":\"visited_expressions_not_exhaustive\","
                    "\"cleanup_object_count_semantics\":\"clang_cleanup_objects_"
                    "not_destructor_event_count\","
                    "\"local_record_object_coverage\":\"visited_local_complete_record_variables_not_exhaustive\","
                    "\"local_record_object_semantics\":\"lexical_declarations_not_runtime_destructor_events\","
                    "\"source_program_checked\":false,"
                    "\"deployable\":false,\"plugin_build_clang_version\":"
                 << llvm::formatv("{0}", llvm::json::Value(CLANG_VERSION_STRING))
                 << ",\"ast_target_triple\":"
                 << llvm::formatv(
                        "{0}", llvm::json::Value(
                                   Context.getTargetInfo().getTriple().str()))
                 << ",\"ast\":";
    Context.getTranslationUnitDecl()->dump(llvm::outs(), false, ADOF_JSON);
    llvm::outs() << ",\"captures\":"
                 << llvm::formatv("{0}",
                                  llvm::json::Value(Visitor.takeCaptures()))
                 << ",\"expression_cleanups\":"
                 << llvm::formatv(
                        "{0}", llvm::json::Value(
                                   Visitor.takeExpressionCleanups()))
                 << ",\"local_record_objects\":"
                 << llvm::formatv("{0}", llvm::json::Value(
                        Visitor.takeLocalRecordObjects()))
                 << "}\n";
  }
};

class CapturePluginAction : public PluginASTAction {
public:
  std::unique_ptr<ASTConsumer>
  CreateASTConsumer(CompilerInstance &, llvm::StringRef) override {
    return std::make_unique<CaptureConsumer>();
  }

  bool ParseArgs(const CompilerInstance &,
                 const std::vector<std::string> &Arguments) override {
    return Arguments.empty();
  }

  ActionType getActionType() override { return ReplaceAction; }
};

} // namespace

static FrontendPluginRegistry::Add<CapturePluginAction>
    Registration("wavebridge-native-captures",
                 "emit a full JSON AST with native lambda capture relations");
