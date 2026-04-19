library TestXorUnique

define Tests: {
    { 0, 0, 0 },
    { 0, 0, 1 },
    { 1, 0, 0 },
    { 1, 0, 1 },
    { 0, 1, 0 },
    { 1, 1, 0 },
    { 0, 1, 1 },
    { 1, 1, 1 }
}

define RunTests:
  Tests T
    return all T[0] = 1 xor T[1] = 1 xor T[2] = 1

define RunTests2:
  Tests T
    return all (T[0] = 1) union (T[1] = 1) union (T[2] = 1)