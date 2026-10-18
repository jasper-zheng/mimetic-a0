# Prompting mimetic-a0

How to prompt **mimetic-a0** (cc0-sampler v4, checkpoint "anneal 120k"). It writes 48 kHz stereo, up to 16 s.

mimetic-a0 learned almost everything it knows from captions written by its own data generators, so it responds best to that wording. This guide gives that wording. Every example under "Tested examples" was generated on two seeds and checked automatically (instrument class with CLAP, plus tempo, pitch or chord where they apply).

## The shape of a prompt

A prompt is a comma-separated list, in this order:

1. **What it is** (the head): the instrument or kit and its role. *"finger bass bassline"*, *"boom bap drum loop"*, *"grand piano chord"*.
2. **The music:** style, chords, feel, density, articulation, dynamics, tone.
3. **Tempo, key and length:** *"90 BPM"*, *"C minor"*, *"4 bars"*.

```
finger bass bassline, over Cm - Fm - G7, sparse, 95 BPM, C minor, 4 bars
```

Keep the head first and in one piece. The other clauses can be in any order and any can be left out (training shuffled and dropped them). A short form works too: the head plus the one fact that matters most.

```
boom bap drum loop, 90 BPM
electric piano chords, Am7 to D7
violin melody, D minor
```

## Length: bars, BPM and duration

Everything is 4/4. Training windows were **1, 2 or 4 bars**, at most 16 s. Set the duration to the bars you ask for:

**seconds = bars × 240 ÷ BPM**

| BPM | 1 bar | 2 bars | 4 bars |
|---|---|---|---|
| 70 | 3.43 | 6.86 | 13.71 |
| 90 | 2.67 | 5.33 | 10.67 |
| 100 | 2.40 | 4.80 | 9.60 |
| 120 | 2.00 | 4.00 | 8.00 |
| 124 | 1.94 | 3.87 | 7.74 |
| 140 | 1.71 | 3.43 | 6.86 |
| 174 | 1.38 | 2.76 | 5.52 |

In the web UI, the **musical fields** on Generate do this for you: set BPM and Bars and the duration follows; Key, Chords, Feel, Density and Dynamics are added to the prompt in the right order. The **"Prompt sent"** line shows exactly what goes to the model. Clear fields you don't want: they stay filled between generations. On the command line, `--bpm 90 --bars 4` does the same: it sets the length and adds "90 BPM, 4 bars" to the prompt if it isn't there.

Tempo comes from the BPM in the text, so other durations work too (the clip just won't end on a bar line). Below 60 BPM, 4 bars no longer fit in 16 s; ask for 2.

## Heads: what it knows

### Beats

`<style> drum loop` plus the kit:

- **Styles:** boom bap, trap, house, techno, disco, breakbeat, drum and bass, jungle, dubstep, afrobeat, reggae one-drop, funk, rock, pop, soul, jazz swing, shuffle. Add *half-time* or *double-time* for those variants ("rock half-time drum loop").
- **Kits:** standard kit (drum kit, acoustic drums), room kit, power kit (big rock drums), electronic kit (electronic drums), 808 kit (808/909 drums, drum machine), dance kit, jazz kit, brush kit (brushes), synth drums.
- **Techniques:** with ghost notes, open hi-hats, cross-stick, on the ride cymbal, hi-hat rolls, fill in the last bar, crash on the downbeat, with shaker, with congas, with cowbell, with tambourine, with clave, with claps, half-time feel, double-time feel.
- **Feel:** straight, swung, heavily swung.

Each style was trained mostly on the kits that suit it (808, electronic and dance kits for trap, house, techno and dubstep; jazz and brush kits for jazz swing; acoustic kits for rock, funk and soul), so those pairings are the strongest.

**One drum on its own:** `<kit> <sound> pattern`, naming what plays: *"808 kit clap and snare pattern"*, *"standard kit kick drum pattern"*, *"dance kit hi-hat pattern"*, *"room kit tambourine and cowbell pattern"*.

**One hit:** `<kit> <voice> hit, one-shot`, optionally *soft* or *hard*. Voices: kick drum, snare, cross-stick, clap, closed hi-hat, pedal hi-hat, open hi-hat, ride cymbal, crash cymbal, high / mid / low / floor tom, tambourine, cowbell, high / low conga, shaker, clave.

### Instruments (one part)

`<instrument> <role>`. Roles: **bassline**, **chords** (rhythmic comping), **held chords** (sustained), **arpeggio**, **melody**, **drum loop**.

| Family | Instruments | Roles |
|---|---|---|
| Bass | acoustic bass, finger bass, pick bass, fretless bass, slap bass, synth bass, acid bass, FM bass, techno bass, pulse bass, saw bass | bassline |
| Keys | grand piano, bright grand piano, electric grand piano, honky-tonk piano, electric piano, FM electric piano, bell piano, harpsichord, clavinet, tonewheel organ, percussive organ, rock organ | chords, held chords, arpeggio, melody |
| Pads | warm pad, fantasia pad, polysynth pad, space voice pad, bowed glass pad, metal pad, halo pad, sweep pad, harpsi pad, solar wind pad, night vision pad, synth pad | held chords |
| Guitar | nylon-string guitar, steel-string acoustic guitar, 12-string guitar, jazz guitar, clean electric guitar, chorused clean guitar, muted electric guitar, funk guitar, overdriven guitar, distorted guitar, wah guitar, ukulele, mandolin, banjo | chords, arpeggio, melody |
| Strings | violin, viola, cello, double bass, pizzicato strings, harp, tremolo strings, string ensemble, slow strings | melody, held chords, arpeggio |
| Brass | trumpet, muted trumpet, trombone, tuba, French horn, brass section | melody, held chords |
| Reeds | soprano / alto / tenor / baritone sax, oboe, English horn, clarinet, bassoon | melody |
| Flutes | flute, piccolo, recorder, pan flute | melody |
| Mallets | vibraphone, marimba, xylophone, glockenspiel, celesta, music box, tubular bells, kalimba | melody, arpeggio, chords |
| Synth leads | square lead, saw lead, sine lead, calliope lead, chiff lead, charang lead, fifths saw lead | melody, arpeggio |
| World | sitar, koto, shamisen, dulcimer | melody, arpeggio |

Single-voice instruments (violin, trumpet, saxes, flutes, synth leads, …) only play melodies and lines, never chords.

### Studio synth voices

From the synth-mode renders (these keep their reverb and delay): **analog mono lead synth**, **soft pulse lead synth** (melody); **plucked arpeggio synth** (chords, arpeggio); **FM bell blip synth**; **CS-80 style brass synth**; **poly synth keys**; **analog bass synth**, **acid bass synth**, **drone bass synth** (bassline); **Juno-style saw pad**, **glass FM pad**, **synth pad** (held chords); **analog drum machine** (drums).

### Electronic tracks

Parts: **drum machine**, **synth bass**, **synth pad**, or single stems *"drum machine kick drum pattern"*, *"drum machine snare pattern"*, *"drum machine hi-hats and percussion"*. Genres: house, techno, disco funk, boom bap hip hop, drum and bass jungle, half-time dubstep, afrobeat, reggae dub, trap. These captions give the key as a root (*"root A"*) and can say *"quartal chords"*, *"open fifths"* or *"unison riff"*.

### Band and orchestral pieces

Instruments named in these captions: grand piano, piano, bright piano, finger bass, pick bass, fretless bass, acoustic upright bass, the kits ("standard kit", "power kit", "jazz kit", "brush kit", …), the GS synth pads ("warm synth pad", "halo synth pad", …), violins, high strings, cellos and basses, string ensemble, pizzicato strings, harp, flute, oboe, clarinet, bassoon, soprano saxophone, french horns, trumpets, trombones, tuba, timpani, choir, marimba, vibraphone, glockenspiel, celesta, xylophone. Mood words for full mixes: lyrical, epic, pulse, arpeggio, ballad, pop, rock, dance pop.

### Mixes

`full mix with A, B and C` (everything playing) or `mix of A and B` (some parts), then the rest as usual. You can say which parts are busy or sparse: *"busy grand piano, sparse finger bass"*.

## The music clauses

| Clause | How to write it | Notes |
|---|---|---|
| Chords (keys, pads, guitars, arpeggios) | `chords Am7 - D7 - Gmaj7` or `Am7 chord` | in the order they play; one per bar or per half bar |
| Chords under a bassline or melody | `over Cm - Fm - G7` | |
| Chord names | C, Cm, Cdim, Caug, Csus2, Csus4, C6, Cm6, Cmaj7, Cm7, C7, Cm7b5, Cdim7, CmMaj7, C7sus4, Cadd9, Cmadd9, C6/9, C9, Cmaj9, Cm9, C7b9, C7#9, C11, Cm11, Cmaj7#11, C13, Cm13, Cmaj13; slash for inversions: Cmaj7/E | flats are written Db, Eb, Gb, Ab, Bb |
| Key | `C minor`, `Eb major` | electronic tracks: `root A` |
| Tempo | `90 BPM` | always capital BPM, a space before it |
| Length | `1 bar`, `2 bars`, `4 bars` | |
| Feel | `straight`, `swung`, `heavily swung`, `laid-back` / `behind the beat` | swing only shows on parts that play off-beats |
| Density | `sparse` / `leaves space` / `minimal`, `busy` / `lots of notes` | |
| Articulation | `smooth, sustained`, `choppy, short notes` | not for decaying sounds like piano or guitar |
| Dynamics | `soft`, `loud` (hits: `soft`, `hard`) | |
| Tone | `warm`, `bright`, `mellow` | |

### One-shots

- **Single note:** `single <instrument> note, <note>`, e.g. *"single cello note, G3"*. Notes are name + octave (C4 is middle C). Optional: soft / loud, warm / bright, low note / high note.
- **Single chord:** `<instrument> chord, <chord name>, <style>`. Styles: *block chord*, *rolled*, *strummed* (guitars), *short stab*. Optional: *first / second / third inversion*, *open voicing*, *soft / loud*, *let ring* (harp, pizzicato). Plain triads and sevenths are the strongest; extended chords (9ths to 13ths) also work.
- **Drum hit:** see Beats above.

## Settings

All testing used **50 steps, CFG 6**, the defaults in the web UI and the CLI. Use several **variations** (takes) per prompt: results vary by seed. Keep a seed to compare checkpoints or wordings on equal terms.

## Tested examples (2 seeds each)

| Prompt | Duration (s) | Result |
|---|---|---|
| boom bap drum loop, standard kit, swung, with ghost notes, 90 BPM, 4 bars | 10.67 | drum loop, tempo right on both |
| house drum loop, dance kit, open hi-hats, 124 BPM, 4 bars | 7.74 | drum loop; tempo right on 1 of 2 |
| jazz swing drum loop, brush kit, heavily swung, 120 BPM, 2 bars | 4.00 | drum loop, tempo right on both |
| techno drum loop, 130 BPM | 7.38 | drum loop, tempo right on both |
| trap drum loop, 808 kit, hi-hat rolls, 140 BPM, 4 bars | 6.86 | drum loop; tempo right on 1 of 2 (see below) |
| drum and bass drum loop, standard kit, with ghost notes, 174 BPM, 4 bars | 5.52 | drum loop; check tempo by ear (see below) |
| 808 kit clap and snare pattern, trap, 140 BPM, 2 bars | 3.43 | drum pattern on both |
| 808 kit kick drum hit, one-shot, hard | 1.0 | single hit on both |
| finger bass bassline, over Cm - Fm - G7, 95 BPM, C minor, 4 bars | 10.11 | bassline on both |
| electric piano chords, chords Am7 - D7 - Gmaj7 - Em7, laid-back, 90 BPM, G major, 4 bars | 10.67 | electric piano on 1 of 2 (see below) |
| warm pad held chords, chords Dm7 - G7 - Cmaj7, soft, 80 BPM, C major, 4 bars | 12.00 | pad on both |
| analog mono lead synth melody, over Am - F - C - G, 110 BPM, A minor, 4 bars | 8.73 | synth lead on both |
| marimba arpeggio, chords C - Am - F - G, 120 BPM, C major, 2 bars | 4.00 | marimba on both |
| violin melody, 100 BPM, D minor, 4 bars | 9.60 | violin on both |
| single grand piano note, C4, soft | 3.0 | piano, right note on both |
| single cello note, G3 | 3.0 | cello, right note on both |
| grand piano chord, Cmaj7, block chord | 3.0 | piano, right chord on both |
| steel-string acoustic guitar chord, G, strummed | 3.0 | guitar, right chord on both |
| full mix with standard kit, finger bass and electric piano, hip hop, chords Fm7 - Bbm7, 88 BPM, Ab major, 4 bars | 10.91 | band with drums to the fore, tempo right on both |
| full mix with drum machine, synth bass and synth pad, house, Am7 chord, 124 BPM, root A, 4 bars | 7.74 | electronic track, drums to the fore, tempo right on both |
| full mix with violins, cellos and basses, french horns and timpani, epic, chords Dm - Bb - C, 90 BPM, D minor, 4 bars | 10.67 | orchestra on 1 of 2 (the other heard as a pad) |

**Check by ear:**
- **Fast and busy beats (trap 140, house 124, drum and bass 174):** the beat tracker often reads them at about 4:5 or 3:2 of the asked tempo, which busy hats and syncopated kicks cause; it cannot say whether the beat is right. Listen, and take several variations.
- **Electric pianos:** CLAP hears the GS electric pianos as organ-like or as a band. Grand piano is the reliable piano.

## Limits

- **Music first.** SFX, foley and field recordings are weak; a separate model or LoRA is planned for them.
- **Wording.** mimetic-a0 follows the vocabulary above best. Far-off phrasings ("120bpm", "strumming", "punchy sub kick") follow less reliably.
- **Timbre.** Most instruments come from the GeneralUser GS SoundFont and sound like General MIDI samples, dry. Only the studio synth voices have reverb and delay.
- **No Amen breaks** (excluded from the training data by policy).
- **4/4 only**, 1, 2 or 4 bars, at most 16 s.
