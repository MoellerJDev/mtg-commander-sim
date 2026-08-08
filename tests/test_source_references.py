from __future__ import annotations

from dataclasses import FrozenInstanceError
import re
import unittest

from quorune.abilities import parse_activated_abilities
from quorune.carddb import CardRecord
from quorune.compiler.counter_placement_templates import (
    CounterPlacementSubject,
    fixed_counter_placement_effect_template,
)
from quorune.compiler.damage_templates import fixed_damage_effect_template
from quorune.compiler.prevention_templates import (
    fixed_prevention_effect_template,
    prevention_trigger_effect_template,
)
from quorune.declaration_costs import normalized_oracle_line
from quorune.declaration_restrictions import parse_declaration_restriction_line
from quorune.oracle_ir import compile_oracle_card
from quorune.rules.source_references import (
    SOURCE_REFERENCE_SCHEMA_VERSION,
    SourceReferenceError,
    SourceReferenceSpec,
)


def card_record(
    *,
    name: str,
    oracle_text: str,
    type_line: str = "Legendary Creature — Human",
) -> CardRecord:
    return CardRecord(
        oracle_id="source-reference-fixture",
        name=name,
        mana_cost="{1}",
        mana_value=1.0,
        type_line=type_line,
        oracle_text=oracle_text,
        power="1" if "Creature" in type_line else None,
        toughness="1" if "Creature" in type_line else None,
        loyalty=None,
        defense=None,
        colors=(),
        color_identity=(),
        keywords=(),
        produced_mana=(),
        layout="normal",
        released_at="2026-01-01",
        legalities={"commander": "legal"},
        faces=(),
        raw={},
    )


class SourceReferenceModelTests(unittest.TestCase):
    def test_full_and_complete_precomma_names_form_closed_vocabulary(self):
        source = SourceReferenceSpec("  Ant-Man,   Scott Lang ")

        self.assertEqual(SOURCE_REFERENCE_SCHEMA_VERSION, source.schema_version)
        self.assertEqual("Ant-Man, Scott Lang", source.full_name)
        self.assertEqual("Ant-Man", source.shortened_name)
        self.assertEqual(
            ("Ant-Man, Scott Lang", "Ant-Man"),
            source.display_names,
        )
        self.assertTrue(source.matches("ant-man, scott lang"))
        self.assertTrue(source.matches("ANT-MAN"))
        self.assertFalse(source.matches("Ant"))
        self.assertFalse(source.matches("Scott Lang"))
        self.assertFalse(source.matches(None))

        equivalent = SourceReferenceSpec("Ant-Man, Scott Lang")
        self.assertEqual(source, equivalent)
        self.assertEqual(hash(source), hash(equivalent))
        with self.assertRaises(FrozenInstanceError):
            source.full_name = "Mutated"  # type: ignore[misc]

    def test_title_delimiter_preserves_complete_name_without_first_word_guess(self):
        source = SourceReferenceSpec("Syr Carah the Bold")

        self.assertEqual(
            ("Syr Carah the Bold", "Syr Carah"),
            source.display_names,
        )
        self.assertTrue(source.matches("Syr Carah the Bold"))
        self.assertTrue(source.matches("Syr Carah"))
        self.assertFalse(source.matches("Syr"))

    def test_bounded_two_word_and_of_title_forms_preserve_existing_oracle_names(self):
        zurgo = SourceReferenceSpec("Zurgo Bellstriker")
        daxos = SourceReferenceSpec("Daxos of Meletis")

        self.assertEqual("Zurgo", zurgo.shortened_name)
        self.assertTrue(zurgo.matches("Zurgo"))
        self.assertEqual("Daxos", daxos.shortened_name)
        self.assertTrue(daxos.matches("Daxos"))

    def test_matching_normalizes_supported_punctuation_only(self):
        source = SourceReferenceSpec("Urza’s Saga")

        self.assertTrue(source.matches("Urza's Saga"))
        self.assertFalse(source.matches("Urzas Saga"))

    def test_regex_pattern_is_escaped_and_closed(self):
        source = SourceReferenceSpec("Karn (Legacy), Silver Golem")

        self.assertIsNotNone(
            re.fullmatch(source.regex_pattern, "Karn (Legacy)", re.IGNORECASE)
        )
        self.assertIsNotNone(
            re.fullmatch(
                source.regex_pattern,
                "Karn (Legacy), Silver Golem",
                re.IGNORECASE,
            )
        )
        self.assertIsNone(
            re.fullmatch(source.regex_pattern, "Karn Legacy", re.IGNORECASE)
        )

    def test_malformed_names_fail_closed(self):
        for value in (None, True, 3, "", "   ", ", Suffix", "Name, "):
            with self.subTest(value=value):
                with self.assertRaises(SourceReferenceError):
                    SourceReferenceSpec(value)  # type: ignore[arg-type]


class SourceReferenceCompilerTests(unittest.TestCase):
    def test_counter_damage_and_prevention_share_shortened_source_identity(self):
        counter = fixed_counter_placement_effect_template(
            "Put a +1/+1 counter on Ant-Man.",
            card_name="Ant-Man, Scott Lang",
        )
        self.assertIsNotNone(counter)
        assert counter is not None
        self.assertIs(CounterPlacementSubject.SOURCE, counter.subject)

        damage = fixed_damage_effect_template(
            "Kamahl deals 3 damage to any target.",
            card_name="Kamahl, Pit Fighter",
        )
        self.assertIsNotNone(damage)
        assert damage is not None
        self.assertEqual("named", damage.source_kind)

        trigger = prevention_trigger_effect_template(
            "Whenever damage that would be dealt to you is prevented, "
            "put that many +1/+1 counters on Ant-Man.",
            card_name="Ant-Man, Scott Lang",
        )
        self.assertIsNotNone(trigger)

        aftermath = fixed_prevention_effect_template(
            "The next time a source of your choice would deal damage to you "
            "this turn, prevent that damage. When damage is prevented this "
            "way, Ant-Man deals that much damage to that source's controller "
            "and you draw that many cards.",
            card_name="Ant-Man, Scott Lang",
        )
        self.assertIsNotNone(aftermath)

    def test_unrelated_or_partial_names_remain_residual(self):
        self.assertIsNone(
            fixed_counter_placement_effect_template(
                "Put a +1/+1 counter on Ant.",
                card_name="Ant-Man, Scott Lang",
            )
        )
        self.assertIsNone(
            fixed_damage_effect_template(
                "Pit Fighter deals 3 damage to any target.",
                card_name="Kamahl, Pit Fighter",
            )
        )
        self.assertIsNone(
            prevention_trigger_effect_template(
                "Whenever damage that would be dealt to you is prevented, "
                "put that many +1/+1 counters on Scott Lang.",
                card_name="Ant-Man, Scott Lang",
            )
        )

    def test_declaration_normalization_accepts_only_complete_precomma_name(self):
        exact = parse_declaration_restriction_line(
            "Syr Carah can't block.",
            card_name="Syr Carah, the Bold",
        )
        guessed = parse_declaration_restriction_line(
            "Syr can't block.",
            card_name="Syr Carah, the Bold",
        )

        self.assertTrue(exact.exact)
        self.assertFalse(guessed.exact)
        self.assertEqual(
            "this creature can't block.",
            normalized_oracle_line(
                "Syr Carah can't block.",
                card_name="Syr Carah, the Bold",
            ),
        )
        self.assertEqual(
            "syr can't block.",
            normalized_oracle_line(
                "Syr can't block.",
                card_name="Syr Carah, the Bold",
            ),
        )

    def test_activated_source_cost_uses_shortened_name_without_guessing(self):
        exact = parse_activated_abilities(
            card_name="Ant-Man, Scott Lang",
            oracle_text="{1}, Sacrifice Ant-Man: Draw a card.",
        )[0]
        guessed = parse_activated_abilities(
            card_name="Ant-Man, Scott Lang",
            oracle_text="{1}, Sacrifice Ant: Draw a card.",
        )[0]

        self.assertTrue(exact.sacrifice_source)
        self.assertTrue(exact.compiled_cost)
        self.assertFalse(guessed.sacrifice_source)
        self.assertFalse(guessed.compiled_cost)
        self.assertEqual(("Sacrifice Ant",), guessed.uncompiled_costs)

    def test_oracle_ir_uses_same_reference_for_trigger_body_and_entry(self):
        trigger_text = (
            "When Ant-Man enters, put a +1/+1 counter on Ant-Man."
        )
        trigger_ir = compile_oracle_card(
            card_record(
                name="Ant-Man, Scott Lang",
                oracle_text=trigger_text,
            )
        )
        trigger_node = next(
            node
            for node in trigger_ir.faces[0].nodes
            if node.template_id
            and node.template_id.startswith("place-fixed-counter-source-")
        )
        self.assertEqual(trigger_text, trigger_node.text)
        self.assertEqual(
            trigger_text,
            trigger_text[trigger_node.span.start : trigger_node.span.end],
        )

        entry_text = "Vault-13 enters tapped."
        entry_ir = compile_oracle_card(
            card_record(
                name="Vault-13, Dwellers' Home",
                oracle_text=entry_text,
                type_line="Legendary Land",
            )
        )
        entry_node = next(
            node
            for node in entry_ir.faces[0].nodes
            if node.template_id == "enters-tapped-self-v1"
        )
        self.assertEqual(entry_text, entry_node.text)
        self.assertEqual(
            entry_text,
            entry_text[entry_node.span.start : entry_node.span.end],
        )

        unsupported = compile_oracle_card(
            card_record(
                name="Vault-13, Dwellers' Home",
                oracle_text="Vault enters tapped.",
                type_line="Legendary Land",
            )
        )
        self.assertFalse(
            any(
                node.template_id == "enters-tapped-self-v1"
                for node in unsupported.faces[0].nodes
            )
        )


if __name__ == "__main__":
    unittest.main()
