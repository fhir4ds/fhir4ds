library Comparisons version '1.0.0'

define "Equality": 'ABC' = 'ABC'
define "Equivalence": 'ABC' ~ 'abc'
define "Absolute Value": Abs(-5)
define "Square Root": Sqrt(16)
define "Power": 2 ^ 3
define "Age Category": if 25 >= 18 then 'Adult' else 'Minor'
define "Grade Category":
  case
    when 85 >= 90 then 'A'
    when 85 >= 80 then 'B'
    when 85 >= 70 then 'C'
    else 'F'
  end
define "Date Difference": difference in days between @2023-01-01 and @2023-01-31
define "Date Range": year from @2024-06-15 = 2024
define "Precedence Test": 2 + 3 * 4
define "Forced Precedence": (2 + 3) * 4
