# Apple-produced `.workout` reference files

Binary files vendored unchanged. `tests/unit/test_workout_file.py` rebuilds each one
byte for byte with `shared.workout_file`, which proves the writer against files that
Apple itself produced. Never edit them: check the SHA-256 below after any copy.

| File | Source repo | Path | Commit | Generator | SHA-256 |
|---|---|---|---|---|---|
| `Run_Average.workout` | [javierferrersb/dotworkout](https://github.com/javierferrersb/dotworkout) | `testdata/Run_Average.workout` | `b36185aa1a98ae992b6c6092c1643e2518b185d8` | real Apple Watch export ("Share workout") | `462cfe698ddc4e7c3c2102672fcb2654423668924b2288a045995a6987767c8e` |
| `ProbeAlertsRange.workout` | [javierferrersb/dotworkout](https://github.com/javierferrersb/dotworkout) | `testdata/ProbeAlertsRange.workout` | `b36185aa1a98ae992b6c6092c1643e2518b185d8` | real Apple Watch export ("Share workout") | `d587f78eb4623b117f5b38af3bc0bf191214b874a08fef17b686ef9e931f0dfc` |
| `Probe_Alerts_Zones.workout` | [javierferrersb/dotworkout](https://github.com/javierferrersb/dotworkout) | `testdata/Probe_Alerts_Zones.workout` | `b36185aa1a98ae992b6c6092c1643e2518b185d8` | real Apple Watch export ("Share workout") | `2728d6a51f9f3a5feb359f6d191a04e3da34a7b79e666bdb83bf47d612db6979` |
| `custom-hiit-mixed.workout` | [bibixx/workoutkit](https://github.com/bibixx/workoutkit) | `samples/from-swift-cli/custom-hiit-mixed.workout` | `1c1c8ae80235c6b7e892d70fe001c49e93183a87` | Apple Swift WorkoutKit (`WorkoutPlan.dataRepresentation`) via the repo's CLI | `5ad2274b2a18e9ff67d088b9aab6f70505a8a28704351e1e7ee27f9473080cb8` |

Check: `sha256sum tests/fixtures/workout/apple/*.workout`

## Licences

The three dotworkout files are distributed under the MIT licence:

    MIT License

    Copyright (c) 2026 Javier Ferrer Sánchez-Barcaiztegui

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

The workoutkit file is distributed under the MIT licence:

    MIT License

    Copyright (c) 2026 Bartosz Legięć

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
