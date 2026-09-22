import copy
import unittest

from wavebridge.analysis.initializer_value import link


def expression(kind, ty, category="prvalue", **fields):
    return dict(kind=kind, type={"qualType": ty}, valueCategory=category, **fields)


def fixture():
    ref = expression("DeclRefExpr", "const Holder", "lvalue",
                     referencedDecl={"id": "object", "kind": "VarDecl"})
    receiver = expression("OpaqueValueExpr", "const Holder", "lvalue", id="opaque", inner=[ref])
    syntax = expression("MSPropertyRefExpr", "<pseudo-object type>", "lvalue", inner=[copy.deepcopy(receiver)])
    member = expression("MemberExpr", "unsigned int ()", "lvalue", isArrow=False,
                        referencedMemberDecl="getter", inner=[copy.deepcopy(receiver)])
    decay = expression("ImplicitCastExpr", "unsigned int (*)()", castKind="FunctionToPointerDecay", inner=[member])
    call = expression("CallExpr", "unsigned int", id="call", inner=[decay])
    pseudo = expression("PseudoObjectExpr", "unsigned int", id="pseudo", inner=[syntax, receiver, call])
    outer = expression("ImplicitCastExpr", "const int", castKind="IntegralCast", inner=[pseudo])
    declaration = {"kind": "CXXMethodDecl", "id": "getter", "storageClass": "static", "inner": []}
    root = {"kind": "TranslationUnitDecl", "inner": [declaration]}
    return root, outer


def add_receiver_declaration(root, initializer_ast, *, ty="const Holder", **fields):
    pseudo = initializer_ast["inner"][0]
    receivers = (pseudo["inner"][0]["inner"][0], pseudo["inner"][1],
                 pseudo["inner"][2]["inner"][0]["inner"][0]["inner"][0])
    for receiver in receivers:
        receiver["inner"][0]["referencedDecl"]["type"] = {"qualType": ty}
    declaration = {"kind": "VarDecl", "id": "object",
                   "type": {"qualType": ty}, "inner": [], **fields}
    declaration.setdefault("storageClass", "extern")
    root["inner"].append(declaration)
    return declaration


class InitializerValueTests(unittest.TestCase):
    def test_exact_extern_receiver_evaluation_is_observed_without_claiming_purity(self):
        root, init = fixture()
        declaration = add_receiver_declaration(root, init)
        declaration["inner"] = [{"kind": "CUDADeviceAttr"}, {"kind": "WeakAttr"}]
        result = link(root, init)
        self.assertEqual(result["status"], "recovered", result)
        observation = result["receiver_evaluation_observation"]
        self.assertEqual(observation["status"], "observed", observation)
        self.assertEqual({key: observation[key] for key in (
            "expression_id", "receiver_id", "receiver_declaration_id",
            "call_id", "callee_declaration_id")}, {
                "expression_id": "pseudo", "receiver_id": "opaque",
                "receiver_declaration_id": "object", "call_id": "call",
                "callee_declaration_id": "getter",
            })
        self.assertIn("initialized", " ".join(observation["premises"]))
        self.assertEqual(result["receiver_purity"], "not_established")

    def test_receiver_observation_failures_do_not_change_legacy_recovery(self):
        cases = {}
        root, init = fixture()
        cases["missing_declaration"] = (root, init)
        root, init = fixture(); declaration = add_receiver_declaration(root, init)
        root["inner"].append(copy.deepcopy(declaration))
        cases["duplicate_id"] = (root, init)
        root, init = fixture(); add_receiver_declaration(root, init, storageClass="static")
        cases["not_extern"] = (root, init)
        root, init = fixture(); add_receiver_declaration(root, init, tls="dynamic")
        cases["thread_local"] = (root, init)
        root, init = fixture(); declaration = add_receiver_declaration(root, init)
        declaration["inner"] = [{"kind": "CallExpr", "inner": []}]
        cases["initializer_child"] = (root, init)
        root, init = fixture(); add_receiver_declaration(root, init, init="c")
        cases["initializer_marker"] = (root, init)
        for name, (root, init) in cases.items():
            with self.subTest(name=name):
                result = link(root, init)
                self.assertEqual(result["status"], "recovered", result)
                self.assertEqual(result["receiver_evaluation_observation"]["status"], "unknown")
                self.assertEqual(result["receiver_purity"], "not_established")

    def test_receiver_semantic_types_references_and_alias_evidence_are_strict(self):
        cases = {}
        root, init = fixture(); add_receiver_declaration(root, init, ty="const Other")
        cases["type_mismatch"] = (root, init)
        root, init = fixture(); declaration = add_receiver_declaration(root, init, ty="const Holder &")
        for receiver in (init["inner"][0]["inner"][0]["inner"][0],
                         init["inner"][0]["inner"][1],
                         init["inner"][0]["inner"][2]["inner"][0]["inner"][0]["inner"][0]):
            receiver["type"] = {"qualType": "const Holder &"}
            receiver["inner"][0]["type"] = {"qualType": "const Holder &"}
        declaration["type"] = {"qualType": "const Holder &"}
        cases["reference"] = (root, init)
        root, init = fixture(); declaration = add_receiver_declaration(root, init, ty="Alias")
        declaration["type"]["typeAliasDeclId"] = "alias"
        cases["alias_without_desugaring"] = (root, init)
        for name, (root, init) in cases.items():
            with self.subTest(name=name):
                result = link(root, init)
                self.assertEqual(result["status"], "recovered", result)
                self.assertEqual(result["receiver_evaluation_observation"]["status"], "unknown")

    def test_receiver_semantic_type_prefers_complete_desugared_evidence(self):
        root, init = fixture()
        declaration = add_receiver_declaration(root, init, ty="Alias")
        pseudo = init["inner"][0]
        receivers = (pseudo["inner"][0]["inner"][0], pseudo["inner"][1],
                     pseudo["inner"][2]["inner"][0]["inner"][0]["inner"][0])
        type_info = {"qualType": "Alias", "desugaredQualType": "const Holder",
                     "typeAliasDeclId": "alias"}
        for receiver in receivers:
            receiver["type"] = copy.deepcopy(type_info)
            receiver["inner"][0]["type"] = copy.deepcopy(type_info)
            receiver["inner"][0]["referencedDecl"]["type"] = copy.deepcopy(type_info)
        declaration["type"] = copy.deepcopy(type_info)
        result = link(root, init)
        self.assertEqual(result["status"], "recovered", result)
        observation = result["receiver_evaluation_observation"]
        self.assertEqual(observation["status"], "observed", observation)
        self.assertEqual(observation["semantic_type"], "const Holder")
    def test_property_links_call_but_not_coordinate_or_converted_value(self):
        root, init = fixture()
        result = link(root, init)
        self.assertEqual(result["status"], "recovered")
        self.assertEqual(result["call_id"], "call")
        self.assertEqual(result["callee_declaration_id"], "getter")
        self.assertEqual(result["conversions_outer_to_inner"][0]["source_type"], "unsigned int")
        self.assertEqual(result["conversions_outer_to_inner"][0]["target_type"], "const int")
        self.assertEqual(result["value_equivalence"], "not_established")
        self.assertEqual(result["coordinate_semantics"], "not_established")
        self.assertEqual(result["receiver_purity"], "not_established")
        self.assertFalse(result["checked"])
        self.assertFalse(result["deployable"])

    def test_wrong_or_missing_result_type_and_category_stay_unknown(self):
        for location in ("pseudo", "call"):
            for field, value in (("type", None), ("type", {"qualType": "float"}),
                                 ("valueCategory", None), ("valueCategory", "lvalue")):
                root, init = fixture()
                pseudo = init["inner"][0]
                node = pseudo if location == "pseudo" else pseudo["inner"][2]
                node[field] = value
                with self.subTest(location=location, field=field, value=value):
                    self.assertEqual(link(root, init)["status"], "unknown")
        root, init = fixture()
        receiver = init["inner"][0]["inner"][1]
        receiver.update(type={"qualType": "unsigned int"}, valueCategory="prvalue")
        self.assertEqual(link(root, init)["reason"], "pseudo_object_result_not_unique_call")

    def test_wrong_shape_and_receiver_are_not_silently_ignored(self):
        for mutation in ("swap", "extra", "missing", "syntax", "member", "effect", "arrow"):
            root, init = fixture()
            children = init["inner"][0]["inner"]
            member = children[2]["inner"][0]["inner"][0]
            if mutation == "swap": children[1], children[2] = children[2], children[1]
            elif mutation == "extra": children.append(copy.deepcopy(children[2]))
            elif mutation == "missing": children.pop(1)
            elif mutation == "syntax": children[0]["inner"][0]["id"] = "other"
            elif mutation == "member": member["inner"][0]["id"] = "other"
            elif mutation == "arrow": member["isArrow"] = True
            else:
                # Even consistently repeated receivers cannot conceal a call.
                for receiver in (children[0]["inner"][0], children[1], member["inner"][0]):
                    receiver["inner"][0]["kind"] = "CallExpr"
            with self.subTest(mutation=mutation):
                self.assertEqual(link(root, init)["status"], "unknown")

    def test_nonstatic_parameterized_missing_and_duplicate_targets_stay_unknown(self):
        for mutation in ("nonstatic", "parameter", "variadic", "missing", "duplicate", "wrong_kind"):
            root, init = fixture()
            method = root["inner"][0]
            if mutation == "nonstatic": method.pop("storageClass")
            elif mutation == "variadic": method["variadic"] = True
            elif mutation == "parameter": method["inner"].append({"kind": "ParmVarDecl"})
            elif mutation == "missing": root["inner"] = []
            elif mutation == "duplicate": root["inner"].append(copy.deepcopy(method))
            else: method["kind"] = "FunctionDecl"
            with self.subTest(mutation=mutation):
                self.assertEqual(link(root, init)["status"], "unknown")

    def test_unsupported_casts_arguments_arithmetic_and_malformed_children(self):
        for mutation in ("outer_cast", "decay", "no_decay", "arg", "arithmetic", "malformed", "depth"):
            root, init = fixture()
            call = init["inner"][0]["inner"][2]
            if mutation == "outer_cast": init["castKind"] = "NoOp"
            elif mutation == "decay": call["inner"][0]["castKind"] = "BitCast"
            elif mutation == "no_decay": call["inner"] = call["inner"][0]["inner"]
            elif mutation == "arg": call["inner"].append({"kind": "IntegerLiteral", "value": "1"})
            elif mutation == "arithmetic": init = {"kind": "BinaryOperator", "opcode": "+", "inner": [init]}
            elif mutation == "malformed": call["inner"].append(None)
            else:
                for _ in range(33): init = expression("ParenExpr", "const int", inner=[init])
            with self.subTest(mutation=mutation):
                self.assertEqual(link(root, init)["status"], "unknown")

    def test_direct_free_call_and_missing_inputs(self):
        call = expression("CallExpr", "int", id="c", inner=[
            {"kind": "DeclRefExpr", "referencedDecl": {"id": "f", "kind": "FunctionDecl"}}])
        root = {"inner": [{"kind": "FunctionDecl", "id": "f"}]}
        self.assertEqual(link(root, call)["status"], "recovered")
        call["valueCategory"] = "lvalue"
        self.assertEqual(link(root, call)["status"], "unknown")
        self.assertEqual(link(None, call)["status"], "unknown")
        self.assertEqual(link(root, None)["status"], "unknown")

    def test_parenthesis_requires_consistent_type_and_value_category(self):
        root, init = fixture()
        paren = expression("ParenExpr", "const int", inner=[init])
        self.assertEqual(link(root, paren)["status"], "recovered")
        for field, value in (("type", None), ("type", {"qualType": "float"}),
                             ("valueCategory", None), ("valueCategory", "lvalue")):
            changed = copy.deepcopy(paren)
            changed[field] = value
            self.assertEqual(link(root, changed)["status"], "unknown")

    def test_receiver_missing_identity_volatile_and_non_lvalue_are_unknown(self):
        for mutation in ("missing_id", "volatile", "non_lvalue"):
            root, init = fixture()
            children = init["inner"][0]["inner"]
            receivers = (children[0]["inner"][0], children[1], children[2]["inner"][0]["inner"][0]["inner"][0])
            for receiver in receivers:
                if mutation == "missing_id": receiver["inner"][0]["referencedDecl"].pop("id")
                elif mutation == "volatile":
                    receiver["type"] = {"qualType": "const volatile Holder"}
                    receiver["inner"][0]["type"] = copy.deepcopy(receiver["type"])
                else: receiver["valueCategory"] = "xvalue"
            self.assertEqual(link(root, init)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
