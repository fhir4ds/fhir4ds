library TestSimpleObservation

using QICore version '6.0.0'

include FHIRHelpers version '4.4.000'

define Test: ["SimpleObservation"] EstimatedDateOfDelivery
  return EstimatedDateOfDelivery.value

