"""
HY-TEK Meet Manager PDF Results Parser

Parses swim meet results PDFs into structured DataFrames.
Handles multi-column layouts (1-col, 2-col, 3-col) common in HY-TEK output.
Supports dual-meet and invitational formats.
"""

import re
import pdfplumber
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


@dataclass
class RelaySwimmer:
    """Relay leg swimmer info"""
    name: str
    year: Optional[str]
    leg: int  # 1-4
    reaction_time: Optional[float] = None


@dataclass
class SwimResult:
    """Individual or relay result"""
    event_number: int
    event_name: str
    event_gender: str
    event_distance: int
    event_stroke: str
    is_relay: bool
    place: Optional[int]
    name: str
    year: Optional[str]
    team: str
    relay_letter: Optional[str]
    finals_time: str
    finals_seconds: Optional[float]
    points: Optional[float]
    time_standard: Optional[str]
    is_exhibition: bool
    is_dq: bool
    is_scratch: bool
    round: Optional[str] = None
    reaction_time: Optional[float] = None
    dq_reason: Optional[str] = None
    splits: list = field(default_factory=list)
    relay_swimmers: List[RelaySwimmer] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def time_to_seconds(time_str: str) -> Optional[float]:
    """Convert time string (MM:SS.ss or SS.ss) to seconds"""
    if not time_str or time_str in ('SCR', 'DQ', 'NS', 'DFS', 'NT'):
        return None
    time_str = time_str.strip().lstrip('x').lstrip('X')
    try:
        if ':' in time_str:
            parts = time_str.split(':')
            minutes = int(parts[0])
            seconds = float(parts[1])
            return round(minutes * 60 + seconds, 2)
        else:
            return round(float(time_str), 2)
    except (ValueError, IndexError):
        return None


TIME_RE = re.compile(r'^x?(\d+:)?\d+\.\d+$')


def looks_like_time(s: str) -> bool:
    """Check if string looks like a swim time"""
    return bool(TIME_RE.match(s.strip()))


# ---------------------------------------------------------------------------
# Column / layout detection
# ---------------------------------------------------------------------------

def detect_layout(pdf) -> Tuple[str, List[float]]:
    """Detect page layout by analysing where lines start on the first few pages.

    Clusters line-start x-positions to find column left edges, then finds
    actual gutter positions in the character density histogram for accurate splits.

    Returns (layout, splits) where:
      - layout: '1col', '2col', or '3col'
      - splits: list of x-coordinates to split columns (gutter centers)
    """
    all_chars = []
    line_starts = []
    for page in pdf.pages[:3]:
        chars = sorted(page.chars, key=lambda c: (c['top'], c['x0']))
        all_chars.extend(chars)
        current_y = None
        y_thresh = 3
        for char in chars:
            if current_y is None or abs(char['top'] - current_y) > y_thresh:
                line_starts.append(char['x0'])
                current_y = char['top']

    if not line_starts:
        return '1col', []

    width = pdf.pages[0].width
    num_bands = 20
    band_width = width / num_bands

    # Build histogram of line-start positions
    bands = [0] * num_bands
    for x in line_starts:
        b = min(int(x / band_width), num_bands - 1)
        bands[b] += 1

    total = len(line_starts)
    min_cluster_pct = 0.04

    # Find clusters with their boundary positions
    clusters = []  # list of (center_x, right_edge_x)
    i = 0
    while i < num_bands:
        if bands[i] > total * min_cluster_pct:
            start = i
            cluster_count = 0
            while i < num_bands and bands[i] > total * min_cluster_pct:
                cluster_count += bands[i]
                i += 1
            if cluster_count > total * 0.08:
                center_x = ((start + i) / 2) * band_width
                right_x = i * band_width
                clusters.append((center_x, right_x))
        else:
            i += 1

    num_clusters = len(clusters)

    if num_clusters >= 3:
        # Find actual gutter positions using character density
        splits = _find_gutter_positions(all_chars, width, num_gutters=2)
        if len(splits) < 2:
            # Fallback: use cluster edges
            splits = []
            for idx in range(len(clusters) - 1):
                gap_center = (clusters[idx][1] + clusters[idx + 1][0]) / 2
                splits.append(gap_center)
        return '3col', splits[:2]
    elif num_clusters == 2:
        split_x = (clusters[0][0] + clusters[1][0]) / 2
        left_count = sum(1 for x in line_starts if x < split_x)
        right_count = sum(1 for x in line_starts if x >= split_x)
        balance = min(left_count, right_count) / max(left_count, right_count) if max(left_count, right_count) else 0
        if balance > 0.30:
            return '2col', [width / 2]
    return '1col', []


def _find_gutter_positions(chars, width, num_gutters=1):
    """Find gutter center x-positions by finding low-density vertical bands
    that have significant content on BOTH sides."""
    num_bands = 60
    band_width = width / num_bands
    bands = [0] * num_bands
    for c in chars:
        b = min(int(c['x0'] / band_width), num_bands - 1)
        bands[b] += 1

    avg = sum(bands) / num_bands if num_bands else 0
    threshold = avg * 0.4

    # Find low-density regions in the interior (10%-90%)
    gutters = []  # (center_x, min_density)
    margin = int(num_bands * 0.10)
    i = margin
    while i < num_bands - margin:
        if bands[i] < threshold:
            start = i
            min_val = bands[i]
            while i < num_bands - margin and bands[i] < threshold:
                min_val = min(min_val, bands[i])
                i += 1
            end = i
            center_x = ((start + end) / 2) * band_width

            # Validate: both sides must have significant content
            check_range = 8
            left_start = max(0, start - check_range)
            right_end = min(num_bands, end + check_range)
            left_avg = sum(bands[left_start:start]) / max(1, start - left_start)
            right_avg = sum(bands[end:right_end]) / max(1, right_end - end)
            min_side = avg * 0.3
            if left_avg > min_side and right_avg > min_side:
                gutters.append((center_x, min_val))
        else:
            i += 1

    # Sort by density (lowest = strongest gutter) and return top N
    gutters.sort(key=lambda g: g[1])
    result = sorted([g[0] for g in gutters[:num_gutters]])
    return result


def extract_columns(page, layout: str, splits: List[float] = None) -> List[str]:
    """Extract text columns from a page based on detected layout and split positions."""
    if layout == '1col':
        text = page.extract_text()
        return [text] if text else []

    width = page.width

    if layout == '2col':
        mid = splits[0] if splits else width / 2
        boundaries = [(0, mid), (mid, width)]
    else:  # 3col
        s1 = splits[0] if splits and len(splits) >= 1 else width / 3
        s2 = splits[1] if splits and len(splits) >= 2 else width * 2 / 3
        boundaries = [(0, s1), (s1, s2), (s2, width)]

    columns = []
    for x0, x1 in boundaries:
        cropped = page.crop((x0, 0, x1, page.height))
        text = cropped.extract_text()
        if text:
            columns.append(text)

    return columns



# ---------------------------------------------------------------------------
# Event header parsing
# ---------------------------------------------------------------------------

def parse_event_header(line: str) -> Optional[dict]:
    """Parse event header line.

    Handles:
      #1 Women 200 Yard Medley Relay
      Event 1 Women 200 Yard Medley Relay
      #15 Women 1 mtr Diving
      Event 15 Women 1 mtr Diving
    """
    line = line.strip()

    # Swimming event: #N or Event N
    pattern = r'(?:#|Event\s+)(\d+)\s+(Women|Men)\s+(\d+)\s+(?:Yard|Meter)\s+(.+)'
    match = re.match(pattern, line)
    if match:
        event_num = int(match.group(1))
        gender = match.group(2)
        distance = int(match.group(3))
        stroke_part = match.group(4).strip()
        is_relay = 'Relay' in stroke_part
        stroke = stroke_part.replace(' Relay', '').strip()

        # Detect and strip Time Trial / Swim-off suffixes
        event_round = None
        if 'Time Trial' in stroke:
            stroke = stroke.replace(' Time Trial', '').strip()
            event_round = 'Time Trial'
        elif 'Swim-off' in stroke or 'Swim-Off' in stroke:
            stroke = re.sub(r'\s*Swim-[Oo]ff', '', stroke).strip()
            event_round = 'Swim-off'

        # Normalise stroke names
        if stroke in ('Free', 'Freestyle'):
            stroke = 'Freestyle'
        elif stroke == 'Back':
            stroke = 'Backstroke'
        elif stroke == 'Breast':
            stroke = 'Breaststroke'
        elif stroke in ('Fly', 'Butterfly'):
            stroke = 'Butterfly'
        elif stroke == 'Medley':
            stroke = 'Medley' if is_relay else 'IM'

        return {
            'event_number': event_num,
            'event_gender': gender,
            'event_distance': distance,
            'event_stroke': stroke,
            'is_relay': is_relay,
            'is_diving': False,
            'event_round': event_round,
            'event_name': f"{gender} {distance} {stroke}" + (" Relay" if is_relay else "")
        }

    # Diving event: "Event N Women 1 mtr Diving" or "Event N Women Platform Diving"
    diving_pattern = r'(?:#|Event\s+)(\d+)\s+(Women|Men)\s+(\d+)\s+mtr\s+Diving'
    match = re.match(diving_pattern, line)
    if match:
        return {
            'event_number': int(match.group(1)),
            'event_gender': match.group(2),
            'event_distance': int(match.group(3)),
            'event_stroke': 'Diving',
            'is_relay': False,
            'is_diving': True,
            'event_name': f"{match.group(2)} {match.group(3)}m Diving"
        }

    platform_pattern = r'(?:#|Event\s+)(\d+)\s+(Women|Men)\s+Platform\s+Diving'
    match = re.match(platform_pattern, line)
    if match:
        return {
            'event_number': int(match.group(1)),
            'event_gender': match.group(2),
            'event_distance': 0,
            'event_stroke': 'Diving',
            'is_relay': False,
            'is_diving': True,
            'event_name': f"{match.group(2)} Platform Diving"
        }

    return None


# ---------------------------------------------------------------------------
# Continued event header  e.g. "(Event 3 Women 200 ..." or "(#3 Women 200 ..."
# ---------------------------------------------------------------------------

_CONT_EVENT_RE = re.compile(r'^\((?:#|Event\s+)(\d+)\s+(Women|Men)')

# ---------------------------------------------------------------------------
# Round / section header detection
# ---------------------------------------------------------------------------

_ROUND_PATTERNS = [
    (re.compile(r'^[ABC]\s*-\s*Final', re.IGNORECASE), 'Finals'),
    (re.compile(r'^Prelim', re.IGNORECASE), 'Prelim'),
    (re.compile(r'^Consolation', re.IGNORECASE), 'Finals'),
    (re.compile(r'^Timed\s+Finals', re.IGNORECASE), 'Finals'),
]


def detect_round(line: str) -> Optional[str]:
    """Check if line is a round/section header. Returns round name or None."""
    line = line.strip()
    for pat, round_name in _ROUND_PATTERNS:
        if pat.match(line):
            return round_name
    return None


# ---------------------------------------------------------------------------
# Header / skip-line detection
# ---------------------------------------------------------------------------

_SKIP_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'HY-TEK',
        r'MEET MANAGER',
        r'Page\s+\d',
        r'Results\s*-',
        r'Site License',
        r'Aquatic Center',
        r'^\d{4}-\d{4}',
        r'^Team\s+R\s*elay',
        r'^Name\s+(?:Y\s*r|Age)',
        r'Scores\s*-',
        r'Team Rankings',
        r'^South Carolina',
        r'^Georgia Institute',
        # Section headers (A-Final, Prelim, etc.) handled as round markers in parse_text_block
        r'^Seed\s+Time',
        r'^Finals\s+Time',
        r'^\s*\d{4}\s+GT\s+The',    # meet title line
        r'^Friday\s+Round',
        r'^Saturday\s+Round',
        r'UGA\s+Fall\s+Invitational',
        r'Ramsey\s+Center',
        r'^McAuley',
    ]
]


def is_header_line(line: str) -> bool:
    """Check if line is a page header, column header, or metadata to skip."""
    line = line.strip()
    if not line:
        return True
    for pat in _SKIP_PATTERNS:
        if pat.search(line):
            return True
    # Time standard line like "1:36.24 A" or "16:25.29 NCAA"
    if re.match(r'^[\d:\.]+\s+(?:A|B|NCAA|RELB|RELA)$', line):
        return True
    # Just a cut standard like "52.65 A"
    if re.match(r'^\d+\.\d+\s+[A-Z]+$', line) and len(line) < 25:
        return True
    return False


# ---------------------------------------------------------------------------
# DQ reason detection
# ---------------------------------------------------------------------------

_DQ_KEYWORDS = [
    'cycle:', 'stroke:', 'turn:', 'start:', 'finish:',
    'pull', 'kick', 'touch', 'delay', 'false',
    'alternating', 'scissors', 'flutter', 'dolphin',
    'not simultaneous', 'did not', 'early', 'late',
    'one hand', 'non-simultaneous', 'past vertical',
]


def is_dq_reason_line(line: str) -> bool:
    lower = line.strip().lower()
    return any(kw in lower for kw in _DQ_KEYWORDS)


# ---------------------------------------------------------------------------
# Split parsing
# ---------------------------------------------------------------------------

def parse_splits(line: str) -> Tuple[list, Optional[float]]:
    """Parse split times and reaction time from a line.

    Returns (splits, reaction_time).

    When parenthesized diff values are present (e.g. HY-TEK relay format),
    returns the actual split/diff times: bare values NOT followed by a paren
    plus all parenthesized values.  This avoids reliance on cumulative values
    which can be dropped by PDF text extraction.

    Without parens, returns bare values as-is.
    """
    line = line.strip()

    # Extract reaction time prefix
    reaction_time = None
    r_match = re.match(r'^r:([+\-]?\d+\.?\d*)\s*', line)
    if r_match:
        try:
            reaction_time = float(r_match.group(1))
        except ValueError:
            pass
        line = line[r_match.end():]

    # Tokenize into bare and paren values, preserving order
    tokens = []  # list of ('bare'|'paren', raw_string)
    pos = 0
    while pos < len(line):
        while pos < len(line) and line[pos].isspace():
            pos += 1
        if pos >= len(line):
            break
        if line[pos] == '(':
            end = line.find(')', pos)
            if end == -1:
                break
            tokens.append(('paren', line[pos + 1:end]))
            pos = end + 1
        else:
            end = pos
            while end < len(line) and not line[end].isspace() and line[end] != '(':
                end += 1
            tokens.append(('bare', line[pos:end]))
            pos = end

    has_parens = any(k == 'paren' for k, _ in tokens)

    splits = []
    if has_parens:
        # Prefer diff/split values: include parenthesized times and bare
        # values NOT followed by ANY paren (even empty ones).
        # A bare value followed by a paren is always a cumulative value.
        for i, (kind, value) in enumerate(tokens):
            if kind == 'paren':
                secs = time_to_seconds(value)
                if secs is not None and 10 <= secs <= 1200:
                    splits.append(secs)
            else:  # bare
                secs = time_to_seconds(value)
                if secs is not None and 10 <= secs <= 1200:
                    # Skip if next token is ANY paren (bare before paren = cumulative)
                    next_is_paren = (i + 1 < len(tokens) and tokens[i + 1][0] == 'paren')
                    if not next_is_paren:
                        splits.append(secs)
    else:
        # No parenthesized values — return bare values as-is
        for _, value in tokens:
            secs = time_to_seconds(value)
            if secs is not None and 10 <= secs <= 1200:
                splits.append(secs)

    return splits, reaction_time


def is_split_line(line: str) -> bool:
    """Check if line contains split times."""
    line = line.strip()
    if not line:
        return False

    # Lines starting with a place number + space + letter are result lines, not splits
    # e.g. "11 University of Florida C 3:13.00 3:12.29 14"
    # Also handle * tie indicator prefix: "*37 Gerhard, Ben ..."
    if re.match(r'^\*?(\d+|---)\s+[A-Za-z]', line):
        return False

    # Starts with reaction time -> likely a split line
    if re.match(r'^r:[+\-]?\d+\.?\d*', line):
        return True

    # Strip reaction prefix for further checks
    cleaned = re.sub(r'^r:[+\-]?\d+\.?\d*\s*', '', line)
    # Remove parenthesized diffs
    cleaned = re.sub(r'\([^)]+\)', '', cleaned).strip()

    if not cleaned:
        return False

    parts = cleaned.split()
    if len(parts) < 2:
        return False

    time_count = sum(1 for p in parts if time_to_seconds(p) is not None and 10 <= time_to_seconds(p) <= 1200)
    return time_count >= 2 and time_count >= len(parts) * 0.5


# ---------------------------------------------------------------------------
# Relay swimmer parsing
# ---------------------------------------------------------------------------

def parse_relay_swimmers(line: str) -> List[Tuple[str, Optional[str], Optional[int], Optional[float]]]:
    """Parse relay swimmer line into list of (name, year_or_age, leg_number, reaction_time).

    Handles:
      Rothwell, Vivien E JR Deedy, Anne SR
      1) Stanisavljevic, Nina SO 2) Reis, Giovana SO
      1) Jones, Emily 22 2) r:0.22 Scott, Jada 20
      1) Sikes, Katie Belle B 20 2) r:0.28 Headland, Charlotte 19
      1) Jones, Emily 22 2) r:0.22 Scott, Jada 20 3) r:0.41 Van Brunt, Gaby 20
      1) Paradis, Mazie 18 2) r:0.25 Blackhurst, Sydney 20 3) r:0.17 Chavez-Varela, Isabella 184) r:0.04 Parker, Sarah 18
    """
    swimmers = []

    # Fix merged age+leg: "184)" → "18 4)", "204)" → "20 4)"
    line = re.sub(r'(\d{2})(\d\))', r'\1 \2', line)

    # Check for numbered format: split by leg markers
    if re.search(r'\d\)', line):
        # Split into segments by leg markers: 1) ... 2) ... 3) ... 4) ...
        parts = re.split(r'(\d)\)', line)
        # parts = ['', '1', ' content1 ', '2', ' content2 ', ...]
        i = 1
        while i < len(parts) - 1:
            leg_num = int(parts[i])
            content = parts[i + 1].strip()

            # Extract reaction time prefix
            reaction = None
            r_match = re.match(r'r:[+\-]?\d+\.?\d*\s*', content)
            if r_match:
                rt_str = r_match.group(0).strip()
                # Parse numeric value: "r:0.22" -> 0.22, "r:+0.54" -> 0.54, "r:-0.39" -> -0.39
                rt_val = re.search(r'[+\-]?\d+\.?\d*', rt_str)
                if rt_val:
                    try:
                        reaction = float(rt_val.group(0))
                    except ValueError:
                        pass
                content = content[r_match.end():].strip()

            # Parse name and age/year from remaining content
            # Name: everything up to the last age/year token
            m = re.match(r'^(.+?)\s+(\d{2}|FR|SO|JR|SR|GS)\s*$', content)
            if m:
                name = m.group(1).strip()
                year_age = m.group(2)
                if ',' in name:
                    swimmers.append((name, year_age, leg_num, reaction))

            i += 2
        if swimmers:
            return swimmers

    # Fallback: un-numbered format — "Name, First [M] YR Name, First YR"
    pattern = r'([A-Za-z\'\-]+,\s*[A-Za-z]+(?:\s+[A-Z])?)\s+(FR|SO|JR|SR|GS|\d{2})'
    matches = re.findall(pattern, line)
    for name, year in matches:
        name = name.strip()
        if ',' in name:
            swimmers.append((name, year, None, None))

    return swimmers


def is_relay_swimmer_line(line: str) -> bool:
    """Check if line contains relay swimmer names."""
    line = line.strip()
    # Numbered format: "1) Name," or "1) r:0.XX Name,"
    if re.search(r'^\d\)\s*(?:r:[+\-]?\d+\.?\d*\s+)?[A-Za-z\'\-]+', line) and ',' in line:
        return True
    # Un-numbered: two names with years
    if re.search(r'[A-Za-z\'\-]+,\s+[A-Za-z]+.*?(FR|SO|JR|SR)\s+[A-Za-z\'\-]+,', line):
        return True
    # Single name with year (last swimmer line)
    if re.match(r'^[A-Za-z\'\-]+,\s+[A-Za-z]+.*?(FR|SO|JR|SR|GS|\d{2})$', line):
        return True
    return False


# ---------------------------------------------------------------------------
# Individual result parsing
# ---------------------------------------------------------------------------

def parse_individual_result(line: str, event_info: dict, fmt: str) -> Optional[SwimResult]:
    """Parse individual event result line.

    fmt: '3col', '2col', or '1col' — determines which patterns to try.

    Dual-meet formats:
      1 Rothwell, Vivien E JR GTCH 54.00 16
      1 Crush, Johnny R SO ARMY 47.79 16
      --- Kling, Joey T SR ARMY SCR
    Invitational format:
      1 Dobson, Kennedi F 18 Georgia, University of 9:29.94 15:47.61 20
      14 Matheson, Thomas Z 18 Florida State University 9:20.21 15:16.40 3
      *37 Gerhard, Ben M 22 Georgia Institute of Technolog 46.53 45.47
    """
    line = line.strip()
    if not line:
        return None

    # Strip leading * (tie indicator) before parsing
    line = line.lstrip('*')

    # Fix split decimal points from PDF extraction: "2. 50" -> "2.50"
    line = re.sub(r'(\d+)\.\s+(\d+)\s*$', r'\1.\2', line)

    result = None

    if fmt == '1col':
        result = _parse_individual_invitational(line, event_info)
    if not result:
        result = _parse_individual_dual(line, event_info)
    return result


def _parse_individual_invitational(line: str, event_info: dict) -> Optional[SwimResult]:
    """Parse invitational format: Place Name Age School SeedTime FinalTime [Points]

    Also handles:
      - Hyphenated first names (Liberty-Belle)
      - NP as seed (No Prior / diving)
      - DQ followed by actual time: "Seed DQ 13:33.61"
      - DQ without time: "Seed DQ" or "Seed DQ DQ"
    """
    # Name pattern: allow spaces, hyphens, apostrophes in surnames (e.g. "Agundez Mora,")
    # and hyphens in first names (e.g. "Liberty-Belle")
    name_pat = r'([A-Za-z\'\-]+(?:\s[A-Za-z\'\-]+)*,\s*[A-Za-z\s\.\-]+?)'

    place_str = name = age = school = seed = finals = points_str = None

    # Time prefix: x=exhibition, J=judge's time
    _tp = r'[xXJ]?'  # time prefix

    # Pattern 1 (most specific): DQ with actual time
    # "--- Name Age School Seed DQ ActualTime"
    if 'DQ' in line:
        m = re.match(
            r'^(\d+|---)\s+'
            + name_pat +
            r'\s+(\d{1,2})\s+'
            r'(.+?)\s+'
            r'(' + _tp + r'(?:\d+:)?\d+\.\d+|NT|NP)\s+'
            r'DQ\s+'
            r'((?:\d+:)?\d+\.\d+)'
            r'(?:\s+(\d+\.?\d*))?'
            r'\s*$',
            line
        )
        if m:
            place_str, name, age, school, seed = (
                m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
            finals = m.group(6)  # actual DQ time
            points_str = m.group(7)
            place = int(place_str) if place_str != '---' else None
            school = school.strip().rstrip(',')
            return SwimResult(
                event_number=event_info['event_number'],
                event_name=event_info['event_name'],
                event_gender=event_info['event_gender'],
                event_distance=event_info['event_distance'],
                event_stroke=event_info['event_stroke'],
                is_relay=False, place=place, name=name.strip(), year=age,
                team=school, relay_letter=None, finals_time=finals,
                finals_seconds=time_to_seconds(finals),
                points=float(points_str) if points_str else None,
                time_standard=None,
                is_exhibition=False, is_dq=True, is_scratch=False,
            )

        # Pattern 2: DQ without actual time (optional seed, optional double-DQ)
        # "--- Name Age School [Seed] DQ [DQ]"
        m = re.match(
            r'^(\d+|---)\s+'
            + name_pat +
            r'\s+(\d{1,2})\s+'
            r'(.+?)\s+'
            r'(?:(' + _tp + r'(?:\d+:)?\d+\.\d+|NT|NP)\s+)?'  # optional seed
            r'DQ'
            r'(?:\s+DQ)?'                              # optional second DQ
            r'\s*$',
            line
        )
        if m:
            place_str, name, age, school, seed = (
                m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
            finals = 'DQ'
            points_str = None
            place = int(place_str) if place_str != '---' else None
            school = school.strip().rstrip(',')
            return SwimResult(
                event_number=event_info['event_number'],
                event_name=event_info['event_name'],
                event_gender=event_info['event_gender'],
                event_distance=event_info['event_distance'],
                event_stroke=event_info['event_stroke'],
                is_relay=False, place=place, name=name.strip(), year=age,
                team=school, relay_letter=None, finals_time='DQ',
                finals_seconds=None,
                points=None,
                time_standard=None,
                is_exhibition=False, is_dq=True, is_scratch=False,
            )

    # Pattern 2b: DFS (Declared False Start) — with or without seed time
    # "--- Name Age School [Seed] DFS"
    if 'DFS' in line:
        m = re.match(
            r'^(\d+|---)\s+'
            + name_pat +
            r'\s+(\d{1,2})\s+'
            r'(.+?)\s+'
            r'(?:(' + _tp + r'(?:\d+:)?\d+\.\d+|NT|NP)\s+)?'  # optional seed
            r'DFS'
            r'\s*$',
            line
        )
        if m:
            place_str, name, age, school, seed = (
                m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
            place = int(place_str) if place_str != '---' else None
            school = school.strip().rstrip(',')
            return SwimResult(
                event_number=event_info['event_number'],
                event_name=event_info['event_name'],
                event_gender=event_info['event_gender'],
                event_distance=event_info['event_distance'],
                event_stroke=event_info['event_stroke'],
                is_relay=False, place=place, name=name.strip(), year=age,
                team=school, relay_letter=None, finals_time='DFS',
                finals_seconds=None,
                points=None,
                time_standard=None,
                is_exhibition=False, is_dq=False, is_scratch=True,
            )

    # Pattern 3 (main): Place Name Age School Seed Final [Points]
    # DQ removed from seed alternatives to prevent school absorbing seed time
    m = re.match(
        r'^(\d+|---)\s+'                     # place
        + name_pat +                          # name (Last, First M)
        r'\s+(\d{1,2})\s+'                   # age
        r'(.+?)\s+'                           # school (non-greedy middle)
        r'(' + _tp + r'(?:\d+:)?\d+\.\d+|NT|NP|SCR)\s+'  # seed time (no DQ)
        r'(' + _tp + r'(?:\d+:)?\d+\.\d+|SCR|DQ|DFS|NS)'  # finals time
        r'(?:\s+(\d+\.?\d*))?'               # optional points
        r'\s*$',
        line
    )
    if m:
        place_str, name, age, school, seed, finals, points_str = (
            m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6), m.group(7))
    else:
        # Pattern 4 (fallback): no seed time column
        m = re.match(
            r'^(\d+|---)\s+'
            + name_pat +
            r'\s+(\d{1,2})\s+'
            r'(.+?)\s+'
            r'(' + _tp + r'(?:\d+:)?\d+\.\d+|SCR|DQ|DFS|NS)'
            r'(?:\s+(\d+\.?\d*))?'
            r'\s*$',
            line
        )
        if m:
            place_str, name, age, school, finals, points_str = (
                m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6))
            seed = None
        else:
            # Pattern 5 (last resort): no age column (rare PDF anomaly)
            # e.g. "8 Agundez Mora, Jesus University of Florida 369.38 337.25 11"
            m = re.match(
                r'^(\d+|---)\s+'
                + name_pat +
                r'\s+'
                r'(.+?)\s+'
                r'(' + _tp + r'(?:\d+:)?\d+\.\d+|NT|NP|SCR)\s+'
                r'(' + _tp + r'(?:\d+:)?\d+\.\d+|SCR|DQ|DFS|NS)'
                r'(?:\s+(\d+\.?\d*))?'
                r'\s*$',
                line
            )
            if m:
                place_str, name, school, seed, finals, points_str = (
                    m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6))
                # Reject if school starts with a digit (likely a mismatched age-based line)
                if school.strip()[0].isdigit():
                    return None
                age = None
            else:
                return None

    place = int(place_str) if place_str != '---' else None
    is_exhibition = finals.startswith('x') or finals.startswith('X')
    finals_clean = finals.lstrip('xXJ')
    is_scratch = finals_clean in ('SCR', 'DFS', 'NS')
    is_dq = finals_clean in ('DQ',)

    # Clean up school name (may have trailing spaces or truncation)
    school = school.strip().rstrip(',')

    return SwimResult(
        event_number=event_info['event_number'],
        event_name=event_info['event_name'],
        event_gender=event_info['event_gender'],
        event_distance=event_info['event_distance'],
        event_stroke=event_info['event_stroke'],
        is_relay=False,
        place=place,
        name=name.strip(),
        year=age,
        team=school,
        relay_letter=None,
        finals_time=finals_clean,
        finals_seconds=time_to_seconds(finals_clean),
        points=float(points_str) if points_str else None,
        time_standard=None,
        is_exhibition=is_exhibition,
        is_dq=is_dq,
        is_scratch=is_scratch,
    )


def _parse_individual_dual(line: str, event_info: dict) -> Optional[SwimResult]:
    """Parse dual-meet format: Place Name [MI] Year Team Time [Standard] [Points]"""
    # Handle DQ lines
    has_dq = 'DQ' in line and 'SCR' not in line

    # Main pattern — flexible team code (with or without dash)
    pattern = (
        r'^(\d+|---)\s+'                     # place
        r'(.+?)\s+'                           # name blob (name + year + team)
        r'(x|X)?'                             # exhibition marker
        r'((?:\d+:)?\d+\.\d+|DQ|SCR|NS)\s*'  # time
        r'([A-Z]+)?\s*'                       # time standard (A, B, NCAA, etc.)
        r'(\d+\.?\d*)?'                       # points
        r'\s*$'
    )
    match = re.match(pattern, line)

    # DQ with time after DQ marker
    if not match and has_dq:
        pattern_dq = r'^(\d+|---)\s+(.+?)(DQ)\s*((?:\d+:)?\d+\.\d+)?\s*([A-Z]+)?\s*(\d+\.?\d*)?\s*$'
        match = re.match(pattern_dq, line)
        if match:
            place_str = match.group(1)
            name_blob = match.group(2).strip()
            time_str = match.group(4) if match.group(4) else 'DQ'
            time_standard = match.group(5)
            points_str = match.group(6)
            place = int(place_str) if place_str != '---' else None
            name, year, team = _extract_name_year_team(name_blob)
            return SwimResult(
                event_number=event_info['event_number'],
                event_name=event_info['event_name'],
                event_gender=event_info['event_gender'],
                event_distance=event_info['event_distance'],
                event_stroke=event_info['event_stroke'],
                is_relay=False, place=place, name=name, year=year, team=team,
                relay_letter=None, finals_time=time_str,
                finals_seconds=time_to_seconds(time_str),
                points=float(points_str) if points_str else None,
                time_standard=time_standard,
                is_exhibition=False, is_dq=True, is_scratch=False,
            )

    if not match:
        return None

    place_str = match.group(1)
    name_blob = match.group(2).strip()
    exh = match.group(3)
    time_str = match.group(4)
    time_standard = match.group(5)
    points_str = match.group(6)

    place = int(place_str) if place_str != '---' else None
    is_exhibition = exh is not None
    is_scratch = time_str == 'SCR'
    is_dq = time_str == 'DQ' or 'DQ' in name_blob

    name, year, team = _extract_name_year_team(name_blob)

    return SwimResult(
        event_number=event_info['event_number'],
        event_name=event_info['event_name'],
        event_gender=event_info['event_gender'],
        event_distance=event_info['event_distance'],
        event_stroke=event_info['event_stroke'],
        is_relay=False, place=place, name=name, year=year, team=team,
        relay_letter=None, finals_time=time_str,
        finals_seconds=time_to_seconds(time_str),
        points=float(points_str) if points_str else None,
        time_standard=time_standard,
        is_exhibition=is_exhibition, is_dq=is_dq, is_scratch=is_scratch,
    )


def _extract_name_year_team(blob: str) -> Tuple[str, Optional[str], str]:
    """Extract (name, year, team) from a combined string.

    Handles spaces between fields AND merged fields (common in 3-col PDFs):
      'Rothwell, Vivien E JR GTCH'        -> name=Rothwell, Vivien E, yr=JR, team=GTCH
      'Crush, Johnny R SO ARMY'            -> name=Crush, Johnny R, yr=SO, team=ARMY
      'Prosinski, Raymond P JR SCAR-SC'    -> name=Prosinski, Raymond P, yr=JR, team=SCAR-SC
      'Brown, Allison SR GTCH'             -> name=Brown, Allison, yr=SR, team=GTCH
      'Richardson, Chris ESRGTCH-GA'       -> name=Richardson, Chris E, yr=SR, team=GTCH-GA
      'Dalton, Alexis S FRSCAR-SC'         -> name=Dalton, Alexis S, yr=FR, team=SCAR-SC
    """
    blob = blob.strip()
    years = ('FR', 'SO', 'JR', 'SR', 'GS')

    # Strategy 1: Try to find year+team merged pattern
    # Look for year code (FR/SO/JR/SR/GS) followed by team code (2-5 uppercase + optional -XX)
    merged = re.search(
        r'(FR|SO|JR|SR|GS)([A-Z]{2,5}-[A-Z]{2}|[A-Z]{2,5})\s*$',
        blob
    )
    if merged:
        year = merged.group(1)
        team = merged.group(2)
        name = blob[:merged.start()].strip()
        if ',' in name:  # Validate we have a real name
            name = re.sub(r'\s+', ' ', name).strip()
            return name, year, team

    # Strategy 2: For dash team codes (TEAM-XX), find the dash and try different
    # team lengths, checking if a year code exists in the chars before the team.
    dash_m = re.search(r'-([A-Z]{2})\s*$', blob)
    if dash_m:
        dash_pos = dash_m.start()
        best_no_year = None  # Fallback: (name, team_code) with no year found

        # Try team lengths 5 down to 2 (longest first for correct team codes)
        for team_len in range(5, 1, -1):
            team_start = dash_pos - team_len
            if team_start < 0:
                continue
            team_code = blob[team_start:dash_m.end()]
            if not re.match(r'^[A-Z]{2,5}-[A-Z]{2}$', team_code):
                continue
            before_team = blob[:team_start].strip()
            if ',' not in before_team:
                continue

            # Check for year code at end of before_team (may be adjacent)
            found_year = False
            for y in years:
                if before_team.endswith(' ' + y):
                    name = before_team[:-(len(y) + 1)].strip()
                    return re.sub(r'\s+', ' ', name), y, team_code
                if before_team.endswith(y):
                    name = before_team[:-len(y)].strip()
                    if ',' in name:
                        return re.sub(r'\s+', ' ', name), y, team_code

            # Strategy 3: Handle garbled char order from overlapping positions.
            # When middle initial + year + team merge (e.g. "SER" for E+SR),
            # look for year code as any 2-char subsequence in the last 3-4 chars.
            suffix = before_team.split()[-1] if before_team.split() else ''
            if 2 <= len(suffix) <= 4 and suffix.isupper():
                for y in years:
                    if y[0] in suffix and y[1] in suffix:
                        idx0 = suffix.index(y[0])
                        idx1 = suffix.index(y[1], idx0 + 1) if y[1] in suffix[idx0+1:] else -1
                        if idx1 > idx0:
                            remaining = suffix[:idx0] + suffix[idx0+1:idx1] + suffix[idx1+1:]
                            name_base = ' '.join(before_team.split()[:-1])
                            if remaining:
                                name_base += ' ' + remaining
                            if ',' in name_base:
                                return re.sub(r'\s+', ' ', name_base), y, team_code

            # Track best no-year result (prefer shortest team code = most common)
            if best_no_year is None and ',' in before_team:
                best_no_year = (re.sub(r'\s+', ' ', before_team), team_code)

        # No team_len yielded a year; use best fallback
        if best_no_year:
            return best_no_year[0], None, best_no_year[1]

    # Strategy 4: Standard approach — find team code (no dash) at end
    team_m = re.search(r'\s([A-Z]{2,6})\s*$', blob)
    if team_m:
        team = team_m.group(1)
        before_team = blob[:team_m.start()].strip()
        year = None
        name = before_team
        for y in years:
            if before_team.endswith(' ' + y):
                year = y
                name = before_team[:-(len(y) + 1)].strip()
                break
            if before_team.endswith(y) and len(before_team) > len(y):
                year = y
                name = before_team[:-len(y)].strip()
                break
        name = re.sub(r'\s+', ' ', name).strip()
        return name, year, team

    # Fallback: no team found
    name = re.sub(r'\s+', ' ', blob).strip()
    return name, None, ''


# ---------------------------------------------------------------------------
# Relay result parsing
# ---------------------------------------------------------------------------

def parse_relay_result(line: str, event_info: dict, fmt: str) -> Optional[SwimResult]:
    """Parse relay event result line.

    Dual-meet: 1 GTCH A 1:29.62 22
    Invitational: 1 University of Alabama A 1:34.59 1:34.37 40
    DQ: --- ARMY A DQ 1:33.34
    NS: --- ARMY B NS
    """
    line = line.strip()
    if not line:
        return None

    # Strip leading * (tie indicator)
    line = line.lstrip('*')

    result = None
    if fmt == '1col':
        result = _parse_relay_invitational(line, event_info)
    if not result:
        result = _parse_relay_dual(line, event_info)
    return result


def _parse_relay_invitational(line: str, event_info: dict) -> Optional[SwimResult]:
    """Invitational relay: Place Team-Full-Name Relay SeedTime FinalTime [Points]"""
    m = re.match(
        r'^(\d+|---)\s+'
        r'(.+?)\s+'                          # team name (may contain spaces)
        r'([A-D])\s+'                         # relay letter
        r'((?:\d+:)?\d+\.\d+|NT|DQ|NS)\s+'   # seed time
        r'(x?(?:\d+:)?\d+\.\d+|DQ|NS|SCR)'   # finals time
        r'(?:\s+(\d+\.?\d*))?'
        r'\s*$',
        line
    )
    if not m:
        return None

    place_str, team, relay, seed, finals, points_str = m.groups()
    place = int(place_str) if place_str != '---' else None
    is_exhibition = finals.startswith('x') or finals.startswith('X')
    finals_clean = finals.lstrip('xX')
    is_dq = finals_clean == 'DQ'
    is_scratch = finals_clean in ('SCR', 'NS')

    return SwimResult(
        event_number=event_info['event_number'],
        event_name=event_info['event_name'],
        event_gender=event_info['event_gender'],
        event_distance=event_info['event_distance'],
        event_stroke=event_info['event_stroke'],
        is_relay=True, place=place, name=team.strip(), year=None,
        team=team.strip(), relay_letter=relay,
        finals_time=finals_clean,
        finals_seconds=time_to_seconds(finals_clean),
        points=float(points_str) if points_str else None,
        time_standard=None,
        is_exhibition=is_exhibition, is_dq=is_dq, is_scratch=is_scratch,
    )


def _parse_relay_dual(line: str, event_info: dict) -> Optional[SwimResult]:
    """Dual-meet relay: Place TEAM Relay [x]Time [Points]"""
    # Flexible team code (with or without dash)
    m = re.match(
        r'^(\d+|---)\s+'
        r'([A-Z][A-Za-z]{1,30}(?:-[A-Z]{2})?)\s+'   # team code
        r'([A-D])\s+'                                  # relay letter
        r'(x|X)?'                                      # exhibition
        r'((?:\d+:)?\d+\.\d+|DQ|NS|SCR)'              # time
        r'(?:\s+((?:\d+:)?\d+\.\d+))?'                 # optional second time (DQ actual time)
        r'(?:\s+(\d+\.?\d*))?'                          # points
        r'\s*$',
        line
    )
    if not m:
        return None

    place_str = m.group(1)
    team = m.group(2)
    relay = m.group(3)
    exh = m.group(4)
    time1 = m.group(5)
    time2 = m.group(6)
    points_str = m.group(7)

    place = int(place_str) if place_str != '---' else None
    is_exhibition = exh is not None
    is_dq = time1 == 'DQ'
    is_scratch = time1 in ('SCR', 'NS')

    # For DQ with actual time: "DQ 1:33.34" -> finals_time is the actual time
    finals = time2 if is_dq and time2 else time1

    return SwimResult(
        event_number=event_info['event_number'],
        event_name=event_info['event_name'],
        event_gender=event_info['event_gender'],
        event_distance=event_info['event_distance'],
        event_stroke=event_info['event_stroke'],
        is_relay=True, place=place, name=team, year=None, team=team,
        relay_letter=relay, finals_time=finals,
        finals_seconds=time_to_seconds(finals),
        points=float(points_str) if points_str else None,
        time_standard=None,
        is_exhibition=is_exhibition, is_dq=is_dq, is_scratch=is_scratch,
    )


# ---------------------------------------------------------------------------
# Diving result parsing
# ---------------------------------------------------------------------------

def parse_diving_result(line: str, event_info: dict) -> Optional[SwimResult]:
    """Parse diving event result line. Handles J-prefix scores."""
    line = line.strip()
    if not line:
        return None

    pattern = r'^(\d+|---)\s+(.+?)\s+(x)?J?([\d\.]+|SCR)\s*(\d+\.?\d*)?\s*$'
    match = re.match(pattern, line)
    if not match:
        return None

    place_str = match.group(1)
    place = int(place_str) if place_str != '---' else None
    name_blob = match.group(2)
    exh = match.group(3)
    score_str = match.group(4)
    points_str = match.group(5)

    name, year, team = _extract_name_year_team(name_blob)
    is_scratch = score_str == 'SCR'

    return SwimResult(
        event_number=event_info['event_number'],
        event_name=event_info['event_name'],
        event_gender=event_info['event_gender'],
        event_distance=event_info['event_distance'],
        event_stroke=event_info['event_stroke'],
        is_relay=False, place=place, name=name, year=year, team=team,
        relay_letter=None,
        finals_time=score_str,
        finals_seconds=float(score_str) if score_str not in ('SCR', 'DQ') else None,
        points=float(points_str) if points_str else None,
        time_standard=None,
        is_exhibition=exh is not None, is_dq=False, is_scratch=is_scratch,
    )


# ---------------------------------------------------------------------------
# Main parsing loop
# ---------------------------------------------------------------------------

def parse_text_block(text: str, event_map: dict, last_event: Optional[dict],
                     fmt: str, last_round: Optional[str] = None) -> Tuple[List[SwimResult], Optional[dict], Optional[str]]:
    """Parse a block of text (one column) into results.

    Returns (results, last_event, last_round).
    """
    results = []
    current_event = last_event
    current_round = last_round
    current_result = None
    pending_relay_swimmers = []
    relay_leg = 1

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Round/section header (A-Final, Prelim, etc.)
        round_name = detect_round(line)
        if round_name:
            current_round = round_name
            continue

        if is_header_line(line):
            continue

        # DQ reason line (right after DQ result)
        if current_result and current_result.is_dq and is_dq_reason_line(line):
            current_result.dq_reason = line
            continue

        # Continued event header: (Event 3 Women ...) or (#3 Women ...)
        cont = _CONT_EVENT_RE.match(line)
        if cont:
            event_num = int(cont.group(1))
            if event_num in event_map:
                _flush(results, current_result, pending_relay_swimmers)
                current_result = None
                pending_relay_swimmers = []
                relay_leg = 1
                current_event = event_map[event_num]
            continue

        # New event header
        event_info = parse_event_header(line)
        if event_info:
            _flush(results, current_result, pending_relay_swimmers)
            current_result = None
            pending_relay_swimmers = []
            relay_leg = 1
            current_event = event_info
            current_round = event_info.get('event_round')  # Time Trial / Swim-off from header, or None
            event_map[event_info['event_number']] = event_info
            continue

        if not current_event:
            continue

        # Skip diving events entirely
        if current_event.get('is_diving', False):
            continue

        # Split line
        if is_split_line(line):
            if current_result:
                splits, reaction = parse_splits(line)
                current_result.splits.extend(splits)
                if reaction is not None and current_result.reaction_time is None:
                    current_result.reaction_time = reaction
            continue

        # Relay swimmer line (must not start with a place number for non-numbered format)
        if current_event['is_relay'] and is_relay_swimmer_line(line) and not re.match(r'^\d+\s+[A-Z]', line):
            swimmers = parse_relay_swimmers(line)
            for name, year_age, leg_num, reaction in swimmers:
                actual_leg = leg_num if leg_num else relay_leg
                pending_relay_swimmers.append(RelaySwimmer(
                    name=name, year=year_age, leg=actual_leg, reaction_time=reaction))
                if leg_num is None:
                    relay_leg += 1
                else:
                    relay_leg = leg_num + 1
            continue

        # Try parsing as result
        result = None
        if current_event['is_relay']:
            result = parse_relay_result(line, current_event, fmt)
            if result:
                _flush(results, current_result, pending_relay_swimmers)
                pending_relay_swimmers = []
                relay_leg = 1
        else:
            result = parse_individual_result(line, current_event, fmt)

        if result:
            result.round = current_round
            if current_result and not current_event['is_relay']:
                results.append(current_result)
            current_result = result

    _flush(results, current_result, pending_relay_swimmers)
    return results, current_event, current_round


def _flush(results, current_result, pending_swimmers):
    """Append current result to results list, attaching any pending relay swimmers."""
    if current_result:
        if pending_swimmers:
            current_result.relay_swimmers = list(pending_swimmers)
        results.append(current_result)


# ---------------------------------------------------------------------------
# Meet info extraction
# ---------------------------------------------------------------------------

def extract_meet_info(pdf_path: str) -> dict:
    """Extract meet name and date from the PDF header."""
    meet_info = {'meet_name': None, 'meet_date': None}

    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return meet_info

        text = pdf.pages[0].extract_text()
        if not text:
            return meet_info

        lines = text.split('\n')

        for line in lines[:15]:
            line = line.strip()
            if not line:
                continue
            if any(skip in line for skip in ['HY-TEK', 'MEET MANAGER', 'Site License', 'Page ']):
                continue

            # Date pattern: M/D/YYYY or MM/DD/YYYY
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', line)
            if date_match and not meet_info['meet_date']:
                meet_info['meet_date'] = date_match.group(1)
                name_part = re.sub(r'\s*[-–]\s*\d{1,2}/\d{1,2}/\d{4}.*', '', line).strip()
                if not name_part:
                    name_part = re.sub(r'\d{1,2}/\d{1,2}/\d{4}', '', line).strip()
                    name_part = re.sub(r'\s*[-–]\s*$', '', name_part).strip()
                # Handle date ranges like "11/18/2025 to 11/21/2025"
                name_part = re.sub(r'\d{1,2}/\d{1,2}/\d{4}\s+to\s+\d{1,2}/\d{1,2}/\d{4}', '', name_part).strip()
                name_part = re.sub(r'\s*[-–]\s*$', '', name_part).strip()
                if name_part and len(name_part) > 3 and not meet_info['meet_name']:
                    meet_info['meet_name'] = name_part
                continue

            # Date pattern: YYYY-MM-DD
            date_match2 = re.search(r'(\d{4}-\d{2}-\d{2})', line)
            if date_match2 and not meet_info['meet_date']:
                meet_info['meet_date'] = date_match2.group(1)
                continue

            # Meet name heuristic
            if not meet_info['meet_name']:
                is_meet_name = (
                    len(line) > 10 and
                    not line.startswith('#') and
                    not line.startswith('Event') and
                    not re.match(r'^\d+\s+', line) and
                    'Results' not in line and
                    ('vs' in line.lower() or '@' in line or 'meet' in line.lower() or
                     'invitational' in line.lower() or 'championship' in line.lower() or
                     'dual' in line.lower() or 'tournament' in line.lower())
                )
                if is_meet_name:
                    meet_info['meet_name'] = line

        # Fallback meet name
        if not meet_info['meet_name']:
            for line in lines[:10]:
                line = line.strip()
                if (line and len(line) > 15 and
                    not any(skip in line for skip in ['HY-TEK', 'MEET MANAGER', 'Site License', 'Page ', 'Results'])):
                    meet_info['meet_name'] = line
                    break

    return meet_info


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_hytek_pdf(pdf_path: str, include_meet_info: bool = False):
    """Parse HY-TEK Meet Manager PDF results into a DataFrame.

    Returns DataFrame, or (DataFrame, meet_info) if include_meet_info=True.
    """
    meet_info = extract_meet_info(pdf_path) if include_meet_info else None

    with pdfplumber.open(pdf_path) as pdf:
        fmt, splits = detect_layout(pdf)

        # First pass: collect event headers
        event_map = {}
        for page in pdf.pages:
            for col_text in extract_columns(page, fmt, splits):
                for line in col_text.split('\n'):
                    ei = parse_event_header(line.strip())
                    if ei:
                        event_map[ei['event_number']] = ei

        # Second pass: parse results
        all_results = []
        last_event = None
        last_round = None

        for page in pdf.pages:
            for col_text in extract_columns(page, fmt, splits):
                results, last_event, last_round = parse_text_block(
                    col_text, event_map, last_event, fmt, last_round)
                all_results.extend(results)

    if not all_results:
        empty = pd.DataFrame()
        return (empty, meet_info) if include_meet_info else empty

    df = pd.DataFrame([{
        'event_number': r.event_number,
        'event_name': r.event_name,
        'event_gender': r.event_gender,
        'event_distance': r.event_distance,
        'event_stroke': r.event_stroke,
        'is_relay': r.is_relay,
        'place': r.place,
        'name': r.name,
        'year': r.year,
        'team': r.team,
        'relay_letter': r.relay_letter,
        'finals_time': r.finals_time,
        'finals_seconds': r.finals_seconds,
        'points': r.points,
        'time_standard': r.time_standard,
        'is_exhibition': r.is_exhibition,
        'is_dq': r.is_dq,
        'is_scratch': r.is_scratch,
        'round': r.round,
        'reaction_time': r.reaction_time,
        'dq_reason': r.dq_reason,
        'splits': r.splits,
        'relay_swimmers': [(s.name, s.year, s.leg, s.reaction_time) for s in r.relay_swimmers] if r.relay_swimmers else [],
    } for r in all_results])

    df = df.drop_duplicates(subset=['name', 'event_name', 'finals_time', 'round'], keep='first')

    # Fix known PDF truncations in team names
    _TEAM_FIXES = {
        'Georgia Institute of Technolog': 'Georgia Institute of Technology',
    }
    if 'team' in df.columns:
        df['team'] = df['team'].replace(_TEAM_FIXES)

    df = df.sort_values(['event_number', 'place']).reset_index(drop=True)

    if include_meet_info:
        return df, meet_info
    return df


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def get_individual_results(df): return df[~df['is_relay']].copy()
def get_relay_results(df): return df[df['is_relay']].copy()
def get_event_results(df, n): return df[df['event_number'] == n].copy()
def get_swimmer_results(df, name): return df[df['name'].str.contains(name, case=False, na=False)].copy()
def get_team_results(df, team): return df[df['team'].str.contains(team, case=False, na=False)].copy()


def summarize_meet(df):
    return {
        'total_results': len(df),
        'events': df['event_name'].nunique(),
        'teams': df['team'].nunique(),
        'individual_results': len(get_individual_results(df)),
        'relay_results': len(get_relay_results(df)),
    }


if __name__ == "__main__":
    import sys
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "data/USC @TECH RESULTS.pdf"

    print(f"Parsing: {pdf_path}")
    df = parse_hytek_pdf(pdf_path)

    if df.empty:
        print("No results found!")
    else:
        s = summarize_meet(df)
        print(f"\n=== Meet Summary ===")
        for k, v in s.items():
            print(f"  {k}: {v}")

        print("\n=== Events Found ===")
        events = df.groupby(['event_number', 'event_name']).size().reset_index(name='count')
        for _, row in events.iterrows():
            print(f"  #{row['event_number']}: {row['event_name']} ({row['count']} results)")

        print("\n=== Sample Results ===")
        ind = get_individual_results(df)
        if len(ind):
            print(ind[['place', 'name', 'year', 'team', 'event_name', 'finals_time', 'points']].head(15).to_string(index=False))

        print("\n=== Sample Relays ===")
        rel = get_relay_results(df)
        for _, row in rel.head(3).iterrows():
            print(f"  {row['team']} {row['relay_letter']} - {row['event_name']}: {row['finals_time']}")
            if row['relay_swimmers']:
                for name, year, leg in row['relay_swimmers']:
                    print(f"    Leg {leg}: {name} ({year})")
