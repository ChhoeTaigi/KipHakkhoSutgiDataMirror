"""KPL (Tâi-lô, 臺羅) Unicode → POJ (Pe̍h-ōe-jī) Unicode.

A Python port of the relevant parts of KonvertToPOJ
(lib/KonvertToPOJ in FhlDictHuDataMirror): DirectUnicodeConverter.kplToPoj,
SystemConverter.kplInputToPojInput, ToneMarker.findPojTonePosition and
PojToneMap. Per syllable: strip the tone mark → swap KPL letters for POJ
letters → re-place the tone mark by POJ rules (狗公會曉學台語 Section 21).

Text is converted token by token; anything that is not a valid KPL syllable
(acronyms such as LED or PM, CJK, punctuation) is passed through unchanged.
"""

import re
import unicodedata

# --- Tone marks ---------------------------------------------------------------

_TONE_MARK_NUMBERS = {
    "́": 2, "̀": 3, "̂": 5, "̄": 7,
    "̍": 8, "̆": 9, "̋": 9,
}
_POJ_TONE_COMBINING = {2: "́", 3: "̀", 5: "̂", 7: "̄", 8: "̍", 9: "̆"}
_N_TONE9 = "̋"  # POJ writes tone 9 on n/ng with a double acute

_SUPERSCRIPT_N = "ⁿ"
_DOT_ABOVE_RIGHT = "͘"
_DIAERESIS_BELOW = "̤"
_U_UR, _u_ur = "Ṳ", "ṳ"

# --- Letter mapping (SystemConverter.kplInputToPojInput) -------------------------

_UA_UE_LOWER = re.compile(r"u([aAeE])")
_UA_UE_UPPER = re.compile(r"U([aAeE])")


def kpl_input_to_poj_input(kpl):
    s = kpl
    for a, b in (("tsh", "chh"), ("Tsh", "Chh"), ("TSH", "CHH"),
                 ("ts", "ch"), ("Ts", "Ch"), ("TS", "CH")):
        s = s.replace(a, b)
    s = _UA_UE_LOWER.sub(lambda m: "o" + m.group(1), s)
    s = _UA_UE_UPPER.sub(lambda m: "O" + m.group(1), s)
    for a, b in (("ik", "ek"), ("Ik", "Ek"), ("IK", "EK"),
                 ("ing", "eng"), ("Ing", "Eng"), ("ING", "ENG"),
                 ("IR", "UR"), ("Ir", "Ur"), ("ir", "ur"),
                 ("ER", "OR"), ("Er", "Or"), ("er", "or")):
        s = s.replace(a, b)
    return s


# --- Tone stripping (ToneMarker.stripToneMark) -----------------------------------

def strip_tone_mark(syllable):
    """Return (bare NFC syllable, tone or None); None if two different tones."""
    tone = None
    bare = []
    for c in unicodedata.normalize("NFD", syllable):
        t = _TONE_MARK_NUMBERS.get(c)
        if t is None:
            bare.append(c)
            continue
        if tone is not None and tone != t:
            return None
        tone = t
    return unicodedata.normalize("NFC", "".join(bare)), tone


# --- POJ tone placement (ToneMarker.findPojTonePosition) -------------------------

_VOWELS = ("a", "i", "u", "o", "e")
_SEMIVOWELS = ("m", "ng", "n")
_HAIKHAU = ("ur", "or")


def _last_index_of_any(s, needles):
    return max(s.rfind(n) for n in needles)


def _strip_nasal(s):
    return s.replace(_SUPERSCRIPT_N, "")


def _is_checked(lower):
    cleaned = _strip_nasal(lower)
    return bool(cleaned) and cleaned[-1] in "ptkh"


def _find_letter_from_right(s, n):
    pos = len(s) - 1
    count = 0
    while pos >= 0:
        c = s[pos]
        if c in (_SUPERSCRIPT_N, _DOT_ABOVE_RIGHT):
            pass
        elif c.lower() == "g" and pos > 0 and s[pos - 1].lower() == "n":
            count += 1
            if count == n:
                pos -= 1
                break
            pos -= 2
            continue
        else:
            count += 1
            if count == n:
                break
        pos -= 1
    return max(pos, 0)


def find_poj_tone_position(lower):
    """(offset, length) of the letter(s) that carry the tone mark, or None."""
    last_vowel = _last_index_of_any(lower, _VOWELS)
    if last_vowel == -1:
        last_semi = _last_index_of_any(lower, _SEMIVOWELS)
        if last_semi == -1:
            return None
        return last_semi, (2 if "ng" in lower else 1)

    if "ur" in lower or "or" in lower:
        return _last_index_of_any(lower, _HAIKHAU), 2

    adjacent = 1 if last_vowel == 0 or lower[last_vowel - 1] not in "aiueo" else 2
    if adjacent == 1:
        return last_vowel, 1
    if adjacent == 2 and "oo" in lower:
        return last_vowel - 1, 2

    pos2 = _find_letter_from_right(lower, 2)
    char2 = lower[pos2]
    if _is_checked(lower):
        if "iuh" in _strip_nasal(lower):
            return _find_letter_from_right(lower, 2), 1
        if char2 in "iu":
            return _find_letter_from_right(lower, 3), 1
        return pos2, 1
    if char2 == "i":
        return _find_letter_from_right(lower, 1), 1
    return _find_letter_from_right(lower, 2), 1


# --- POJ input → Unicode (ToneMarker.pojInputToUnicode) --------------------------

def _poj_fix_nn(s):
    if "nng" in s.lower():
        return s
    return s.replace("nn", _SUPERSCRIPT_N).replace("NN", _SUPERSCRIPT_N).replace("Nn", _SUPERSCRIPT_N)


def _poj_fix_oo(s):
    if s.isupper():
        return (s.replace("OO", "O" + _DOT_ABOVE_RIGHT)
                 .replace("UR", _U_UR)
                 .replace("OR", "O" + _DIAERESIS_BELOW))
    return (s.replace("Oo", "O" + _DOT_ABOVE_RIGHT)
             .replace("oo", "o" + _DOT_ABOVE_RIGHT)
             .replace("Ur", _U_UR).replace("ur", _u_ur)
             .replace("Or", "O" + _DIAERESIS_BELOW)
             .replace("or", "o" + _DIAERESIS_BELOW))


def _mark(target, tone):
    """Apply a POJ tone mark to a 1–2 letter unit: a, oo, ur, or, m, n, ng (any case)."""
    low = target.lower()
    if low == "oo":
        return unicodedata.normalize("NFC", target[0] + _POJ_TONE_COMBINING[tone] + _DOT_ABOVE_RIGHT)
    if low == "ur":
        return unicodedata.normalize("NFC", (_U_UR if target[0] == "U" else _u_ur) + _POJ_TONE_COMBINING[tone])
    if low == "or":
        mark = "̍̍" if tone == 8 else _POJ_TONE_COMBINING[tone]
        return unicodedata.normalize("NFC", target[0] + _DIAERESIS_BELOW + mark)
    if low == "ng":
        return unicodedata.normalize("NFC", target[0] + _POJ_TONE_COMBINING[tone] + target[1])
    if low == "n":
        mark = _N_TONE9 if tone == 9 else _POJ_TONE_COMBINING[tone]
        return unicodedata.normalize("NFC", target + mark)
    return unicodedata.normalize("NFC", target + _POJ_TONE_COMBINING[tone])


def poj_input_to_unicode(base, tone=None):
    """`base` is POJ letters in input spelling (oo, nn, ur, or); `tone` 1–9 or None."""
    s = _poj_fix_nn(base)
    if tone is None or tone in (1, 4):
        return _poj_fix_oo(s)
    pos = find_poj_tone_position(s.lower())
    if pos is None:
        return _poj_fix_oo(s)
    off, length = pos
    marked = s[:off] + _mark(s[off:off + length], tone) + s[off + length:]
    return _poj_fix_oo(marked)


# --- KPL syllable validation ---------------------------------------------------

# Permissive KPL syllable shape (bare letters, lower case). Acronyms such as
# "led", "pm", "ab", lone consonants ("w", "h", "n") do not match and are kept.
_KPL_SYLLABLE = re.compile(
    r"^(?:tsh|ts|ph|th|kh|ng|p|m|b|t|n|l|k|g|h|s|j)?"
    r"(?:(?:ir|er|[aeiou]+)(?:nn)?(?:ng|m|n|p|t|k|h)?|h?(?:m|ng)h?)$"
)


def is_kpl_syllable(bare):
    return bool(_KPL_SYLLABLE.match(bare.lower()))


# --- Public API ---------------------------------------------------------------

def kpl_syllable_to_poj(syllable):
    stripped = strip_tone_mark(syllable)
    if stripped is None:
        return syllable
    bare, tone = stripped
    if not is_kpl_syllable(bare):
        return syllable
    return poj_input_to_unicode(kpl_input_to_poj_input(bare), tone)


_LOMAJI_RUN = re.compile(r"[A-Za-zÀ-ɏḀ-ỿ̀-ͯⁿ]+")


def kpl_to_poj(text):
    """Convert every KPL syllable in `text`; delimiters and other tokens are kept."""
    return _LOMAJI_RUN.sub(lambda m: kpl_syllable_to_poj(m.group(0)), unicodedata.normalize("NFC", text))


if __name__ == "__main__":
    import sys
    for line in sys.stdin:
        print(kpl_to_poj(line.rstrip("\n")))
