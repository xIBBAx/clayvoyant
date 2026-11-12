# Writing a film with a chat assistant

A film here is a few text files. Writing them is the one part that takes imagination, and it is
also the part any chat assistant can do on a free plan: a two-scene script is about a page of
text. Nothing in this guide sends anything anywhere by itself. You copy a brief out, and you copy
a script back in.

## 1. Print a brief

```bash
sastudio brief my-film "A shopkeeper is told he must enter his PIN to receive a payment" --scenes 2 --seconds 40
```

The brief is a page of Markdown with everything a writer who has never seen this project needs:
your cast (ids, names, roles and how they behave), the places and their marks, the light, the
gestures, the emotions, the cameras, the exact file format with a complete example, and the rules
the validator applies. Every list is read from the same tables the validator uses, so the brief
cannot offer a set, a gesture or a camera that does not exist.

`--out brief.md` writes it to a file instead. `--scenes` takes 1 to 12, `--seconds` 10 to 180.

## 2. Paste it into the assistant you use

Paste the whole brief. Add anything the brief cannot know: who will watch, what they already do
wrong, the procedure your organisation actually follows, the tone. For example:

> The audience is a residents' association, mostly over sixty. Keep every line short. The person
> who explains should be a neighbour, not an expert. End on what to do, not on what went wrong.

The assistant answers with one YAML file per scene and the lines to add to `studio.yaml`.

## 3. Save it and check it

Save each file under `scenes/` with the name the assistant gave it, add the `scenes:` lines to
`studio.yaml`, then:

```bash
sastudio validate my-film          # every unknown set, mark, gesture, emotion or name, with a fix
sastudio direct my-film            # the shot list: read it like a storyboard
```

When `validate` reports a mistake, paste its output back to the assistant and ask for a corrected
file. Two rounds are usually enough.

## 4. Check it like an editor

The validator checks the format, not the truth. Before anyone sees the film:

- **Facts.** Every number, helpline, website and procedure in a line must be right for your
  audience, today. Assistants invent plausible ones. Look each one up at its source.
- **Names.** Names are written as `{id}` tokens. A name typed as plain text is flagged by
  `validate`, because a rename would miss it.
- **Translations.** A line in a second language needs `translations:` and, where numbers or web
  addresses should be read out differently from how they are shown, `spoken:`. Have a fluent
  speaker read every translated line before you film it.
- **Length.** `sastudio voices plan my-film` lists every line with its words. Read them aloud.

## 5. Film it

```bash
sastudio film my-film --preset draft              # clay: look at it, change lines, film again
sastudio render my-film --preset draft            # drawn characters: no Blender, no graphics card
```

Only the shots a change can affect are filmed again, so the second and third drafts are quick.

## Why this costs nothing

The assistant writes words, which every plan includes. The pictures, the voices and the edit are
made on your computer by this project. No video allowance, no per-second price, no queue.
