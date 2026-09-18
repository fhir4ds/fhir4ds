library NullSafety version '1.0.0'

context Patient

define "Deceased Is Null": Patient.deceased is null
define "Explicit Null Is Null": null is null
define "Null Not Equal": null != 'x'
define "Null And False": null and false
define "Null Or True": null or true
define "Null Not Propagates": not null
define "Coalesce First NonNull": Coalesce(null, null, 'found me')
define "Missing Field Is Null": Patient.telecom is null
define "Coalesce Field Default": Coalesce(Patient.deceased.value, 'still alive')
define "Count Ignores Null": Count({null, 'a', null, 'b'})
define "IsNull Vs IsTrue": if (Patient.deceased is null) is true then 'no death date' else 'has death date'
