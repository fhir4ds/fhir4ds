"""HDQT taxonomy v1.0 for PIQI [HB pp.17-19].

Canonical codes and the alias table for the guides' own inconsistent
dimension spellings. This module is the SINGLE SOURCE of dimension
classification (FDD invariant 7): SAM SQL bodies carry mnemonics only,
never ad-hoc dimension strings.
"""

from __future__ import annotations


from typing import Dict


class PIQIDimension:
    """One HDQT dimension: category + dimension + canonical code.

    Simple singleton class (not Enum) so ``.name`` can carry the
    dimension name (Enum reserves ``name`` for the member id).
    """

    _members: list = []

    def __init__(self, category: str, name: str, code: str):
        self.category = category
        self.name = name
        self.code = code
        PIQIDimension._members.append(self)

    @property
    def mnemonic(self) -> str:
        return f"{self.category}.{self.name}"

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"PIQIDimension({self.mnemonic}, {self.code})"


def _dim(category: str, name: str, code: str) -> PIQIDimension:
    return PIQIDimension(category, name, code)


AV_MISS = _dim("Availability", "Missing", "AV-MISS")
AV_UNPOP = _dim("Availability", "Unpopulated", "AV-UNPOP")
AV_INCOMP = _dim("Availability", "Incomplete", "AV-INCOMP")
AV_DUP = _dim("Availability", "Duplication", "AV-DUP")
AC_FMT = _dim("Accuracy", "InvalidFormat", "AC-FMT")
AC_VAL = _dim("Accuracy", "InvalidValue", "AC-VAL")
AC_GRP = _dim("Accuracy", "InvalidGrouping", "AC-GRP")
CF_INVM = _dim("Conformity", "InvalidMember", "CF-INVM")
CF_INCMPT = _dim("Conformity", "Incompatible", "CF-INCMPT")
CF_OBS = _dim("Conformity", "Obsolete", "CF-OBS")
PL_TMP = _dim("Plausibility", "TemporallyImplausible", "PL-TMP")
PL_CLI = _dim("Plausibility", "ClinicallyImplausible", "PL-CLI")
PL_SIT = _dim("Plausibility", "SituationallyImplausible", "PL-SIT")

# Expose singletons as class attributes (PIQIDimension.AV_UNPOP, ...) —
# setattr is required because Enum-style member syntax cannot be used
# (``name`` must carry the dimension name, not the member id).
for _d in list(PIQIDimension._members):
    setattr(PIQIDimension, _d.code.replace("-", "_"), _d)


#: Canonical mnemonics [HB pp.17-19].
_CANONICAL_MNEMONICS: Dict[str, PIQIDimension] = {
    d.mnemonic: d for d in PIQIDimension._members
}

#: Guide-erratum aliases [SG pp.9,11,16-19]: every inconsistent spelling
#: the guides use, normalized to exactly one canonical dimension so an
#: erratum cannot silently split a dimension (FDD test D-26).
_ALIASES: Dict[str, PIQIDimension] = {
    # [SG p.11] "Availablity.Populated" (sic) for the unpopulated check
    "Availablity.Populated": PIQIDimension.AV_UNPOP,
    "Availability.Populated": PIQIDimension.AV_UNPOP,
    # [SG p.17] Concept_HasCode/HasCodeSystem/HasDisplay dimension
    "Availability.IsPopulated": PIQIDimension.AV_UNPOP,
    # [SG p.18] Concept_IsComplete / [SG p.22] RangeValue_IsComplete
    "Availability.Complete": PIQIDimension.AV_INCOMP,
    "Availability.IsComplete": PIQIDimension.AV_INCOMP,
    # [SG pp.18-19] "Conformance" for Conformity
    "Conformance.Invalid": PIQIDimension.CF_INVM,
    "Conformance.Incompatible": PIQIDimension.CF_INCMPT,
    "Conformance.Obsolete": PIQIDimension.CF_OBS,
    "Conformity.Invalid": PIQIDimension.CF_INVM,
    # [SG pp.11-14] positive-name spellings for failure dimensions
    "Accuracy.ValidValue": PIQIDimension.AC_VAL,
    "Accuracy.ValidFormat": PIQIDimension.AC_FMT,
    # [SG p.9] abbreviated Plausibility spellings
    "Plausibility.Clinical": PIQIDimension.PL_CLI,
    "Plausibility.Temporally": PIQIDimension.PL_TMP,
    "Plausibility.Situational": PIQIDimension.PL_SIT,
    "Plausibility.Temporal": PIQIDimension.PL_TMP,
}

_MNEMONICS: Dict[str, PIQIDimension] = {**_CANONICAL_MNEMONICS, **_ALIASES}


def resolve_dimension(mnemonic: str) -> PIQIDimension:
    """Resolve a guide dimension mnemonic/alias to its canonical dimension.

    Raises ``ValueError`` for unknown spellings so a new guide spelling
    cannot silently classify as "unknown".
    """
    try:
        return _MNEMONICS[mnemonic]
    except KeyError:
        raise ValueError(
            f"Unknown HDQT dimension mnemonic {mnemonic!r}; known: "
            f"{sorted(_MNEMONICS)}"
        ) from None


#: Standard SAM catalog → HDQT dimension binding, transcribed from the
#: SAM property tables [SG pp.9-25]. Guide spellings normalized through
#: ``resolve_dimension``.
_SAM_DIMENSIONS: Dict[str, str] = {
    # Simple attribute SAMs [SG pp.11-15]
    "Attr_IsPopulated": "Availability.Unpopulated",  # a.k.a. Availablity.Populated
    "Attr_IsNumeric": "Accuracy.ValidValue",
    "Attr_IsInteger": "Accuracy.ValidValue",
    "Attr_IsDecimal": "Accuracy.ValidValue",
    "Attr_IsPositiveNumber": "Accuracy.ValidValue",
    "Attr_IsNegativeNumber": "Accuracy.ValidValue",
    "Attr_IsDate": "Accuracy.ValidValue",
    "Attr_IsFutureDate": "Accuracy.ValidValue",
    "Attr_IsPastDate": "Accuracy.ValidValue",
    "Attr_IsTime": "Accuracy.ValidValue",
    "Attr_IsTimestamp": "Accuracy.ValidValue",
    "Attr_IsTimestampTz": "Accuracy.ValidValue",
    "Attr_IsValidDate": "Accuracy.InvalidFormat",  # [SG p.9 JSON]
    "Attr_MatchesRegex": "Accuracy.InvalidFormat",
    "Attr_InList": "Accuracy.ValidValue",
    # Codable concept SAMs [SG pp.17-19]
    "Concept_HasCode": "Availability.IsPopulated",
    "Concept_HasCodeSystem": "Availability.IsPopulated",
    "Concept_HasDisplay": "Availability.IsPopulated",
    "Concept_HasRecognizedCodeSystem": "Accuracy.ValidValue",
    "Concept_IsComplete": "Availability.IsComplete",
    "Concept_IsValid": "Conformance.Invalid",
    "Concept_IsValidMember": "Conformance.Incompatible",
    "Concept_IsConsistent": "Accuracy.InvalidValue",
    "Concept_IsActive": "Conformance.Obsolete",
    # Observation value SAMs [SG pp.20-21]
    "ObservationValueType_InList": "Accuracy.InvalidValue",
    "ObservationValue_MatchesType": "Accuracy.InvalidValue",
    "ObservationValue_HasType": "Accuracy.InvalidValue",
    "ObservationValue_IsQualitative": "Accuracy.InvalidValue",
    # Range value SAMs [SG p.22]
    "RangeValue_IsComplete": "Availability.IsComplete",
    "RangeValue_IsValid": "Accuracy.InvalidValue",
    # Element SAMs [SG pp.23-24]
    "Element_IsClean": "Availability.Incomplete",
    "Lab_PlausibleUnit_LOINC_V1": "Plausibility.Clinical",
    "LabResult_UnitIsPlausible": "Plausibility.Clinical",
    "LabResult_ValueIsPlausible": "Plausibility.Clinical",
    "Condition_SexPlausible": "Plausibility.Clinical",
    # Data class SAMs [SG p.25]
    "Class_HasDuplicates": "Availability.Duplication",
    # Patient message SAMs [SG p.26]
    "Patient_IsUndocumentedDiabetic": "Availability.Missing",
}


def dimension_for_sam(sam_mnemonic: str) -> PIQIDimension:
    """Return the HDQT dimension a SAM mnemonic is bound to [SG]."""
    try:
        return resolve_dimension(_SAM_DIMENSIONS[sam_mnemonic])
    except KeyError:
        raise ValueError(
            f"Unknown SAM mnemonic {sam_mnemonic!r}; known: "
            f"{sorted(_SAM_DIMENSIONS)}"
        ) from None


#: Terminology-server-dependent SAMs [SG pp.18-19] — deferred behind a
#: pluggable ``piqi.terminology`` table (FDD §8 Q1, follow-up FHIR4-17).
TERMINOLOGY_DEPENDENT_SAMS = frozenset({
    "Concept_IsValid",
    "Concept_IsValidMember",
    "Concept_IsConsistent",
    "Concept_IsActive",
    "Concept_HasRecognizedCodeSystem",
})

#: RESTful execution type [SG p.26] — out of scope for all phases.
RESTFUL_SAMS = frozenset({"Patient_IsUndocumentedDiabetic"})

__all__ = [
    "PIQIDimension",
    "resolve_dimension",
    "dimension_for_sam",
    "TERMINOLOGY_DEPENDENT_SAMS",
    "RESTFUL_SAMS",
]
