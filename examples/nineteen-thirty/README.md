# Nineteen Thirty

A one-scene clay film about the "digital arrest" scam, in English and Hindi from the same script.

Gopal, a retired schoolteacher, has been on a video call for two hours with a man in a uniform who
says he is under arrest and must transfer his savings to clear his name. His daughter Ira walks in
before any money goes. Fourteen lines, about a minute and a half.

The family and the residents' association are invented. The advice is not: every claim in the
script follows a public advisory, listed in [Films for India](../../docs/INDIA.md#where-the-advice-comes-from).

```bash
pip install -e ".[clay,voices]"
sastudio voices install kokoro
sastudio direct examples/nineteen-thirty                          # the shot list
sastudio film examples/nineteen-thirty --preset draft             # English, 960x540
sastudio film examples/nineteen-thirty --preset draft --lang hi-IN   # Hindi
```

Each film, its subtitles and a transcript land in `examples/nineteen-thirty/build/en-IN/` and
`build/hi-IN/`.

## What to look at

| In the files | On screen |
|---|---|
| `languages: [en-IN, hi-IN]`, `translations:` on every line | two films from one script; Hindi voices and Devanagari subtitles in the second |
| `voice: ... languages: { hi-IN: ... }` | each character has an English voice and a Hindi one |
| `spoken:` on three lines | the subtitles show "1930" and "sancharsaathi.gov.in"; the voices say "nineteen thirty" and "उन्नीस तीस", and spell the address out |
| `act: [phone_to_ear]` on Gopal's first two lines | he is on the call, and we hear only his side of it |
| `act: [walk_in]` on Ira's first line | she is not in the room until then: the planner keeps the opening shots on Gopal alone |
| `blocking: { gopal: sofa, ira: sofa_side }` | he sits facing the room; she arrives to stand beside him |
| `outfit: { style: vest }`, `extras: [glasses, moustache]` | a sweater vest over a shirt, round glasses, a white moustache |
| `outfit: { style: kurta }`, `extras: [bindi, earrings]` | a short kurti over jeans |
| `takeaway:` | the key point card: report the caller on Sanchar Saathi; if money has gone, call 1930 at once |

The five-scene version, with a UPI PIN, an OTP, an electricity-bill message and a fake helpline, is
the `india` template: `sastudio init my-film --template india`.
