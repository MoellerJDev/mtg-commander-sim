from __future__ import annotations


# Pinned from Comprehensive Rules 205.3m in the repository's
# 2026-06-19 rules snapshot.  Compiler templates use this closed vocabulary
# instead of treating an arbitrary capitalized adjective as a creature type.
_PINNED_CREATURE_SUBTYPES = """
advisor|aetherborn|alien|ally|angel|antelope|ape|archer|archon|armadillo|army|
artificer|assassin|assembly-worker|astartes|atog|aurochs|avatar|azra|badger|
balloon|barbarian|bard|basilisk|bat|bear|beast|beaver|beeble|beholder|
berserker|bird|bison|blinkmoth|boar|bringer|brushwagg|camarid|camel|capybara|
caribou|carrier|cat|centaur|child|chimera|citizen|cleric|clown|cockatrice|
construct|coward|coyote|crab|crocodile|c’tan|custodes|cyberman|cyclops|dalek|
dauthi|demigod|demon|deserter|detective|devil|dinosaur|djinn|doctor|dog|dragon|
drake|dreadnought|drix|drone|druid|dryad|dwarf|echidna|efreet|egg|elder|
eldrazi|elemental|elephant|elf|elk|employee|eternal|eye|faerie|ferret|fish|
flagbearer|fox|fractal|frog|fungus|gamer|gamma|gargoyle|germ|giant|giraffe|
gith|glimmer|gnoll|gnome|goat|goblin|god|golem|gorgon|graveborn|gremlin|
griffin|guest|hag|halfling|hamster|harpy|hedgehog|hellion|hero|hippo|
hippogriff|homarid|homunculus|horror|horse|human|hydra|hyena|illusion|imp|
incarnation|inhuman|inkling|inquisitor|insect|jackal|jellyfish|juggernaut|
kangaroo|kavu|kirin|kithkin|knight|kobold|kor|kraken|kree|llama|lamia|
lammasu|leech|lemur|leviathan|lhurgoyf|licid|lizard|lobster|manticore|
masticore|mercenary|merfolk|metathran|minion|minotaur|mite|mole|monger|
mongoose|monk|monkey|moogle|moonfolk|mount|mouse|mutant|myr|mystic|
nautilus|necron|nephilim|nightmare|nightstalker|ninja|noble|noggle|nomad|
nymph|octopus|ogre|ooze|orb|orc|orgg|otter|ouphe|ox|oyster|pangolin|peasant|
pegasus|pentavite|performer|pest|phelddagrif|phoenix|phyrexian|pilot|pincher|
pirate|plant|platypus|porcupine|possum|praetor|primarch|prism|processor|qu|
rabbit|raccoon|ranger|rat|rebel|reflection|rhino|rigger|robot|rogue|sable|
salamander|samurai|sand|saproling|satyr|scarecrow|scientist|scion|scorpion|
scout|sculpture|seal|serf|serpent|servo|shade|shaman|shapeshifter|shark|
sheep|shi’ar|siren|skeleton|skrull|skunk|slith|sliver|sloth|slug|snail|
snake|soldier|soltari|sorcerer|spawn|specter|spellshaper|sphinx|spider|spike|
spirit|splinter|sponge|spy|squid|squirrel|starfish|surrakar|survivor|
symbiote|synth|tentacle|tetravite|thalakos|thopter|thrull|tiefling|time lord|
toy|treefolk|trilobite|triskelavite|troll|turtle|tyranid|unicorn|utrom|
vampire|varmint|vedalken|villain|volver|wall|walrus|warlock|warrior|weasel|
weird|werewolf|whale|wizard|wolf|wolverine|wombat|worm|wraith|wurm|yeti|
zombie|zubera
"""

CREATURE_SUBTYPES = frozenset(
    value.strip()
    for value in _PINNED_CREATURE_SUBTYPES.replace("\n", "").split("|")
    if value.strip()
)
CREATURE_SUBTYPE_RULE_REFERENCE = "205.3m"
CREATURE_SUBTYPE_SNAPSHOT = "2026-06-19"


def canonical_creature_subtype(value: str) -> str | None:
    """Return one pinned creature subtype, or ``None`` if unsupported."""

    if type(value) is not str:
        return None
    normalized = " ".join(value.casefold().split())
    return normalized if normalized in CREATURE_SUBTYPES else None


__all__ = [
    "CREATURE_SUBTYPES",
    "CREATURE_SUBTYPE_RULE_REFERENCE",
    "CREATURE_SUBTYPE_SNAPSHOT",
    "canonical_creature_subtype",
]
