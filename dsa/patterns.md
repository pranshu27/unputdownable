# Pattern Ledger — revise before every interview

One entry per problem. **Name the family, not the problem** — interviewers probe transfer, not LC numbers.
Status: ✅ verified · 🟡 attempt in flight · 🔒 locked (unlocked by the entry above it)

---

## Family A — Prefix state + hash map  *(count pairs over full windows)*

| Member | State hashed | "Equal state" means | Status |
| :--- | :--- | :--- | :--- |
| **LC 560** Subarray Sum Equals K | `pre` (look up `pre − k`) | two moments exactly k apart | ✅ P1 |
| **LC 974** Subarray Sums Divisible by K | `pre mod k` | two moments a *multiple of k* apart | ✅ P1.5 |
| **LC 525** Contiguous Array (equal 0s/1s) | `(#0s − #1s)` prefix | equal difference ⇒ balanced window | 🔒 preview |
| **LC 523** Continuous Subarray Sum (mult. of k) | `pre mod k` **+ earliest index** | same, but earliest index ⇒ *longest* | 🔒 preview |
| **Two Sum** | the value itself | `target − x` seen before | 🔒 preview |

**Skeleton (in words):** define a per-index *state* → scan once → **ask the map "who matches me?" BEFORE joining it** → count (or keep earliest index) for each match.

### P1 — LC 560 Subarray Sum Equals K ✅
- **Two make-or-break traps:** seed `{0: 1}` (empty prefix → subarrays starting at index 0); lookup **before** record (`k = 0` self-counts otherwise).
- **Ladder:** brute O(n³) → prefix sums O(n²) → single-pass hashmap O(n). Measured: 2.6 ms vs 5,532 ms at n = 20,000.
- **Why NOT sliding window:** negatives break monotonicity — windows are valid only when all `nums ≥ 0` (cf. LC 209).
- **Complexity:** O(n) time, O(n) space.
- **Soundbite:** *"I went brute force → prefix sums → single-pass hashmap; the seed {0:1} counts the empty prefix so zero-start subarrays aren't missed, and the lookup must precede the insert or k=0 self-counts."*

### P1.5 — LC 974 Subarray Sums Divisible by K ✅
- **Unit change:** hash `pre mod k` — the lens is otherwise identical to P1.
- **Why fold the remainder every step:** `rem` *is* the running total mod k, because `(a+b) mod k = ((a mod k) + b) mod k` — folding early changes nothing (the "keep full prefix, fold at lookup" variant matched on 300/300 fuzz cases). It matters only in fixed-width languages, where the raw prefix can overflow and then the two versions diverge.
- **The pair view:** a stretch is valid iff both ends sit at the same remainder; n moments at one remainder ⇒ 1+2+…+(n−1) pairs.
- **Landmines:** 0 counts as divisible (that's the zero-sum stretch inside a bucket); Python `%` floors (`-1 % 7 == 6`) so **no guard needed in Python** — `((x % k) + k) % k` is a C++/Java necessity, where `%` truncates toward zero and would split one remainder into two buckets.
- **Hand-derived total:** **7** (remainder 0 → A,C,D,G → 3+2+1 = 6; remainder 6 → F,I → 1) — matches brute force.
- **Complexity:** O(n) time, O(min(n, k)) space.
- **Measured:** fuzz 300/300 vs brute force (negatives, k ∈ 1..13); n = 20,000 → **2.2 ms**, while brute force needed 89.5 ms for only n = 2,000.
- **Soundbite:** *"LC 974 is LC 560 with a different equality predicate: equal remainders of the running sum bracket a multiple-of-k stretch, and the seed `{0:1}` is moment 0 — the start of the walk, which really sits at remainder 0."*

---

## Family B — Sliding window  *(maintain + shrink instead of count)*

| Member | Window state | Shrink trigger | Status |
| :--- | :--- | :--- | :--- |
| **LC 3** Longest Substring Without Repeating Characters | last-seen index per char | a duplicate enters | ✅ P2 |
| **LC 209** Min Size Subarray Sum ≥ target | running sum | sum ≥ target | preview (valid: all positive) |
| **LC 438 / 567** Find All Anagrams / Permutation in String | char frequency map | window exceeds pattern length | preview |

**Skeleton (in words):** two pointers → expand right → **while invalid, shrink left** → update the answer on each valid window. Works only when validity is **monotone** in window size (adding elements can't fix a broken window).

### P2 — LC 3 Longest Substring Without Repeating Characters ✅
- **Family change:** no pair counting — maintain ONE window (`left`, `right`): expand right always, shrink left while invalid.
- **Monotonicity (why the window is legal here):** a duplicate can't be fixed by adding more characters ⇒ broken-ness is monotone ⇒ shrinking from the left is justified. Contrast LC 560/974, where "sum = k" can be broken *and* fixed by new elements (negatives), which is exactly why windows are illegal there.
- **Two implementations:** (a) set + shrink-while-loop — easiest to reason about, each char touched ≤ 2n; (b) last-seen-index dict — single pass, `left = max(left, last[c] + 1)`, each char touched once.
- **Landmine (`"abba"`):** drop the `max(...)` and `left` can jump *backwards* to before the current window, wrongly re-admitting a character you had excluded.
- **Input opacity (spaces):** no normalization — `"".join(s.split())` silently deletes spaces (`"a b"` → 2 instead of 3; `"   "` → `-inf` from the `-inf` init). Key the counter by the character (`dict`) so spaces/digits/symbols are representable; `[0]*26` can't even index a space. Also: two consecutive spaces are duplicates of the *same* character (`"a  b"` → 2).
- **Complexity:** V2 O(n) time, O(min(n, alphabet)) space; V1 O(n) time (each char touched <= 2n), O(alphabet) space.
- **Optimal form:** `left = max(left, last.get(c, -1) + 1)`; `last[c] = right`; `best = max(best, right - left + 1)`.
- **Measured:** `"abba"` -> 2 (the no-`max` variant returns 3); fuzz 500/500 vs brute force over letters+digits+symbols+spaces; n = 100,000 in ~11.5 ms (V1: 17.3 ms), while brute force is O(n x alphabet) for small alphabets but truly O(n^2) on all-distinct input (87.2 ms at n=3,000, vs V2 handling n=100,000 in ~11.5 ms).
- **Soundbite:** *"LC 3 is a sliding window: monotone validity (a duplicate can never be repaired by adding characters) lets me shrink from the left; I keep a last-seen index map and update `left = max(left, last[c] + 1)` so `left` never moves backwards - that `max` is the `"abba"` trap."*

---

## Cross-cutting traps — reread these 2 minutes before an interview

1. **Seed / sentinel** — the neutral "state 0" row is always needed; in the pair view it is *moment 0* (the empty prefix / start of the walk), a real moment that can pair with later ones. #1 forgotten line.
2. **Order** — query the map first; insert yourself second.
3. **Equality predicate** — `= k` vs `mod k = 0` vs `equal difference`: same algorithm, different unit. Naming this is the senior signal.
4. **Monotonicity check** — negatives anywhere ⇒ no sliding window ⇒ hashmap pairs.
5. **Language `%` semantics** — Python floors; C++/Java truncate. Know which side of the guard you're on.
6. **Pairs law** — a *window is a pair of moments* (its two ends); n moments at the same state ⇒ 1+2+…+(n−1) = C(n,2) windows close at once (this is all "triangle" ever meant). Count blowups live here (`[0,0,0,0]`, k=0 → 10).
7. **Input opacity + alphabet breadth** — never normalize the input (`split()` / `strip()` / lowercase); treat the string as data (same for arrays: no filtering). And let the alphabet dictate the structure: a fixed `[0]*26` breaks outside a–z (`ord(' ') - ord('a') = -65` → IndexError), so key the counter by the character (`dict`) when the alphabet is open (letters + digits + symbols + spaces).

## How to use this file
- After each drill: fill the entry's blanks, flip 🟡 → ✅, unlock the next 🔒.
- Revision pass: read only the **Skeleton** lines and the **Cross-cutting traps** (2 min), then the table row for whichever family the question smells like.
