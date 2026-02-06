"""
HY-TEK Meet Manager PDF Results Parser

Parses swim meet results PDFs into structured DataFrames.
Handles multi-column layouts common in HY-TEK output.
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
    is_exhibition: bool  # X prefix - non-scoring swim
    is_dq: bool  # DQ - disqualified
    is_scratch: bool  # SCR - did not swim
    dq_reason: Optional[str] = None  # Reason for DQ
    splits: list = field(default_factory=list)
    relay_swimmers: List[RelaySwimmer] = field(default_factory=list)


def time_to_seconds(time_str: str) -> Optional[float]:
    """Convert time string (MM:SS.ss or SS.ss) to seconds"""
    if not time_str or time_str in ('SCR', 'DQ', 'NS', 'DFS'):
        return None
    time_str = time_str.strip()
    try:
        if ':' in time_str:
            parts = time_str.split(':')
            minutes = int(parts[0])
            seconds = float(parts[1])
            return round(minutes * 60 + seconds, 2)  # Round to hundredths
        else:
            return round(float(time_str), 2)
    except (ValueError, IndexError):
        return None


def extract_columns(page) -> List[str]:
    """Extract text from each column of a multi-column page using character positions"""
    chars = page.chars
    if not chars:
        text = page.extract_text()
        return [text] if text else []

    width = page.width

    # HY-TEK uses 3 columns - boundaries at 1/3 and 2/3 of page width
    col1_end = width * 0.33
    col2_end = width * 0.66

    columns = []
    boundaries = [(0, col1_end), (col1_end, col2_end), (col2_end, width)]

    for x_start, x_end in boundaries:
        col_chars = [c for c in chars if x_start <= c['x0'] < x_end]
        if not col_chars:
            continue

        col_chars.sort(key=lambda c: (c['top'], c['x0']))

        lines = []
        current_line = []
        current_y = None
        y_threshold = 3

        for char in col_chars:
            if current_y is None or abs(char['top'] - current_y) <= y_threshold:
                current_line.append(char)
                current_y = char['top'] if current_y is None else current_y
            else:
                if current_line:
                    lines.append(build_line_text(current_line))
                current_line = [char]
                current_y = char['top']

        if current_line:
            lines.append(build_line_text(current_line))

        if lines:
            columns.append('\n'.join(lines))

    return columns


def build_line_text(chars: list) -> str:
    """Build line text from characters, preserving spaces based on gaps"""
    if not chars:
        return ""

    chars = sorted(chars, key=lambda c: c['x0'])
    result = []
    prev_x1 = None
    space_threshold = 3

    for char in chars:
        if prev_x1 is not None:
            gap = char['x0'] - prev_x1
            if gap > space_threshold:
                result.append(' ')
        result.append(char['text'])
        prev_x1 = char['x1']

    return ''.join(result)


def clean_name_year_team(raw_text: str) -> Tuple[str, Optional[str], str]:
    """
    Extract name, year, and team from potentially mangled text.
    Handles cases like:
    - "Prosinski, Raymon JdR PSCAR-SC" -> ("Prosinski, Raymond P", "JR", "SCAR-SC")
    - "Chasser, Caroline SJRSCAR-SC" -> ("Chasser, Caroline S", "JR", "SCAR-SC")
    - "Goodwin-Birnie, E SliOzaSbCeAtR-SC" -> ("Goodwin-Birnie, Elizabeth", "SO", "SCAR-SC")
    """
    # Known team codes
    teams = ['SCAR-SC', 'GTCH-GA']
    years = ['FR', 'SO', 'JR', 'SR', 'GS']

    # First, try to find the team code - it might be mangled
    team = None
    team_idx = -1

    # Look for exact team match first
    for t in teams:
        if t in raw_text:
            team = t
            team_idx = raw_text.find(t)
            break

    # If not found, look for mangled versions like "R-SC" at end
    if not team:
        # Try to find team pattern - might be partially mangled
        team_match = re.search(r'([A-Z]{2,6}-[A-Z]{2})(?:\s|$)', raw_text)
        if team_match:
            team = team_match.group(1)
            team_idx = team_match.start()
        else:
            # Look for "-SC" or "-GA" pattern
            if '-SC' in raw_text:
                team = 'SCAR-SC'
                team_idx = raw_text.find('-SC') - 4  # Approximate
                if team_idx < 0:
                    team_idx = raw_text.find('-SC')
            elif '-GA' in raw_text:
                team = 'GTCH-GA'
                team_idx = raw_text.find('-GA') - 4
                if team_idx < 0:
                    team_idx = raw_text.find('-GA')

    if not team:
        # Try to extract any team-like pattern
        team_match = re.search(r'([A-Z]{2,6}-[A-Z]{2})', raw_text)
        if team_match:
            team = team_match.group(1)
            team_idx = team_match.start()
        else:
            return raw_text, None, ""

    # Get text before team
    before_team = raw_text[:team_idx].strip() if team_idx > 0 else raw_text

    # Look for year code - might be attached to team or separate
    year = None
    name = before_team

    # Check for year at end of before_team
    for y in years:
        if before_team.endswith(y):
            year = y
            name = before_team[:-len(y)].strip()
            break
        if before_team.endswith(' ' + y):
            year = y
            name = before_team[:-len(y)-1].strip()
            break

    # Handle mangled cases where year chars got mixed into garbage
    if not year:
        year_patterns = [
            (r'(\w+)\s+J[dD]R\s+(\w?)', r'\1 \2', 'JR'),
            (r'(\w+)\s+S[oO]R\s+(\w?)', r'\1 \2', 'SR'),
            (r'(\w+)\s+F[rR]R\s+(\w?)', r'\1 \2', 'FR'),
            (r'(\w+)\s+S[oO]\s+(\w?)', r'\1 \2', 'SO'),
        ]
        for pat, repl, yr in year_patterns:
            if re.search(pat, name):
                name = re.sub(pat, repl, name).strip()
                year = yr
                break

    # Clean up badly mangled names - remove garbage characters
    # Pattern: if name has random uppercase letters mixed in, it's mangled
    # e.g., "E SliOzaSbCeAt" -> try to extract just the name part
    if re.search(r'[a-z][A-Z][a-z]', name):  # Mixed case like "SliOza"
        # Keep only the part before the garbage
        comma_idx = name.find(',')
        if comma_idx > 0:
            # Keep last name and try to extract first name
            last_name = name[:comma_idx]
            after_comma = name[comma_idx+1:].strip()
            # Extract first word as first name
            first_name_match = re.match(r'^([A-Z][a-z]+)', after_comma)
            if first_name_match:
                name = f"{last_name}, {first_name_match.group(1)}"
            else:
                # Just keep the last name and first initial if available
                first_init = re.match(r'^([A-Z])', after_comma)
                if first_init:
                    name = f"{last_name}, {first_init.group(1)}."
                else:
                    name = last_name

    # Clean up name - ensure proper spacing
    name = re.sub(r'\s+', ' ', name).strip()

    return name, year, team


def parse_event_header(line: str) -> Optional[dict]:
    """Parse event header line like '#1 Women 200 Yard Medley Relay' or '#15 Women 1 mtr Diving'"""
    # Standard swimming event
    pattern = r'#(\d+)\s+(Women|Men)\s+(\d+)\s+(?:Yard|Meter)\s+(.+)'
    match = re.match(pattern, line.strip())

    if match:
        event_num = int(match.group(1))
        gender = match.group(2)
        distance = int(match.group(3))
        stroke_part = match.group(4).strip()
        is_relay = 'Relay' in stroke_part
        stroke = stroke_part.replace(' Relay', '').replace(' Free', ' Freestyle').strip()
        if stroke == 'Free':
            stroke = 'Freestyle'

        return {
            'event_number': event_num,
            'event_gender': gender,
            'event_distance': distance,
            'event_stroke': stroke,
            'is_relay': is_relay,
            'is_diving': False,
            'event_name': f"{gender} {distance} {stroke}" + (" Relay" if is_relay else "")
        }

    # Diving event
    diving_pattern = r'#(\d+)\s+(Women|Men)\s+(\d+)\s+mtr\s+Diving'
    match = re.match(diving_pattern, line.strip())

    if match:
        event_num = int(match.group(1))
        gender = match.group(2)
        height = int(match.group(3))

        return {
            'event_number': event_num,
            'event_gender': gender,
            'event_distance': height,
            'event_stroke': 'Diving',
            'is_relay': False,
            'is_diving': True,
            'event_name': f"{gender} {height}m Diving"
        }

    return None


def parse_individual_result(line: str, event_info: dict) -> Optional[SwimResult]:
    """Parse individual event result line"""
    line = line.strip()
    if not line:
        return None

    # Check for DQ - has "DQ" in the line (sometimes merged like "SCAR-SCDQ")
    has_dq = 'DQ' in line and 'SCR' not in line

    # More flexible pattern that captures the whole name/year/team blob
    # Pattern: Place [Name blob with year and team] [X]Time [Standard] [Points]
    # Also handle DQ case where time might be "DQ" or merged with team
    pattern = r'^(\d+|---)\s+(.+?)\s+(x|X)?(\d+:?[\d\.]+|DQ|SCR)\s*(A|B)?\s*([\d\.]+)?$'
    match = re.match(pattern, line)

    # Try alternate pattern for DQ merged with team (e.g., "SCAR-SCDQ 2:09.80")
    if not match and has_dq:
        # Pattern: --- Name YEAR TEAM DQ Time
        # The DQ might be merged with team like "SCAR-SCDQ" or "SRSCAR-SCDQ"
        pattern_dq = r'^(\d+|---)\s+(.+?)(DQ)\s*(\d+:?[\d\.]+)?\s*(A|B)?\s*([\d\.]+)?$'
        match = re.match(pattern_dq, line)
        if match:
            place_str = match.group(1)
            name_year_team = match.group(2)
            time_str = match.group(4) if match.group(4) else 'DQ'
            time_standard = match.group(5)
            points_str = match.group(6)

            # Clean up name_year_team - remove any trailing characters before DQ
            name_year_team = name_year_team.strip()

            place = int(place_str) if place_str != '---' else None
            name, year, team = clean_name_year_team(name_year_team)
            points = float(points_str) if points_str else None

            return SwimResult(
                event_number=event_info['event_number'],
                event_name=event_info['event_name'],
                event_gender=event_info['event_gender'],
                event_distance=event_info['event_distance'],
                event_stroke=event_info['event_stroke'],
                is_relay=False,
                place=place,
                name=name,
                year=year,
                team=team,
                relay_letter=None,
                finals_time=time_str,
                finals_seconds=time_to_seconds(time_str),
                points=points,
                time_standard=time_standard,
                is_exhibition=False,
                is_dq=True,
                is_scratch=False,
                dq_reason=None,  # Will be set from next line if available
                splits=[],
                relay_swimmers=[]
            )

    if match:
        place_str = match.group(1)
        place = int(place_str) if place_str != '---' else None
        name_year_team = match.group(2)
        exhibition_marker = match.group(3)
        time_str = match.group(4)
        time_standard = match.group(5)
        points_str = match.group(6)

        # Check if DQ is hidden in the name_year_team blob (e.g., "SRSCAR-SCDQ")
        is_dq_in_blob = 'DQ' in name_year_team

        # Clean up the name/year/team (this will strip out the DQ)
        name, year, team = clean_name_year_team(name_year_team)

        # Determine status: exhibition (X prefix), scratch (SCR), DQ, or normal
        is_exhibition = exhibition_marker is not None  # X or x before time
        is_scratch = time_str == 'SCR'
        is_dq = time_str == 'DQ' or is_dq_in_blob

        points = float(points_str) if points_str else None

        return SwimResult(
            event_number=event_info['event_number'],
            event_name=event_info['event_name'],
            event_gender=event_info['event_gender'],
            event_distance=event_info['event_distance'],
            event_stroke=event_info['event_stroke'],
            is_relay=False,
            place=place,
            name=name,
            year=year,
            team=team,
            relay_letter=None,
            finals_time=time_str,
            finals_seconds=time_to_seconds(time_str),
            points=points,
            time_standard=time_standard,
            is_exhibition=is_exhibition,
            is_dq=is_dq,
            is_scratch=is_scratch,
            splits=[],
            relay_swimmers=[]
        )

    return None


def parse_diving_result(line: str, event_info: dict) -> Optional[SwimResult]:
    """Parse diving event result line"""
    line = line.strip()
    if not line:
        return None

    # Pattern: Place Name TEAM [x]Score [Points]
    # The 'x' prefix indicates exhibition
    pattern = r'^(\d+|---)\s+(.+?)\s+(x)?([\d\.]+|SCR)\s*([\d\.]+)?$'
    match = re.match(pattern, line)

    if match:
        place_str = match.group(1)
        place = int(place_str) if place_str != '---' else None
        name_year_team = match.group(2)
        exhibition_marker = match.group(3)
        score_str = match.group(4)
        points_str = match.group(5)

        name, year, team = clean_name_year_team(name_year_team)
        points = float(points_str) if points_str else None
        is_exhibition = exhibition_marker is not None
        is_scratch = score_str == 'SCR'

        return SwimResult(
            event_number=event_info['event_number'],
            event_name=event_info['event_name'],
            event_gender=event_info['event_gender'],
            event_distance=event_info['event_distance'],
            event_stroke=event_info['event_stroke'],
            is_relay=False,
            place=place,
            name=name,
            year=year,
            team=team,
            relay_letter=None,
            finals_time=score_str,
            finals_seconds=float(score_str) if score_str not in ('SCR', 'DQ') else None,
            points=points,
            time_standard=None,
            is_exhibition=is_exhibition,
            is_dq=False,
            is_scratch=is_scratch,
            splits=[],
            relay_swimmers=[]
        )

    return None


def parse_relay_result(line: str, event_info: dict) -> Optional[SwimResult]:
    """Parse relay event result line"""
    line = line.strip()
    if not line:
        return None

    # Pattern: Place TEAM Relay Time [Points]
    pattern = r'^(\d+)\s+([A-Z]{2,6}-[A-Z]{2})\s+([A-C])\s+(x)?(\d+:[\d\.]+)\s*([\d\.]+)?'
    match = re.match(pattern, line)

    if match:
        place = int(match.group(1))
        team = match.group(2)
        relay_letter = match.group(3)
        exhibition_marker = match.group(4)
        time_str = match.group(5)
        points_str = match.group(6)

        is_exhibition = exhibition_marker is not None
        points = float(points_str) if points_str else None

        return SwimResult(
            event_number=event_info['event_number'],
            event_name=event_info['event_name'],
            event_gender=event_info['event_gender'],
            event_distance=event_info['event_distance'],
            event_stroke=event_info['event_stroke'],
            is_relay=True,
            place=place,
            name=team,
            year=None,
            team=team,
            relay_letter=relay_letter,
            finals_time=time_str,
            finals_seconds=time_to_seconds(time_str),
            points=points,
            time_standard=None,
            is_exhibition=is_exhibition,
            is_dq=False,
            is_scratch=False,
            splits=[],
            relay_swimmers=[]
        )

    return None


def parse_relay_swimmers(line: str) -> List[Tuple[str, Optional[str]]]:
    """
    Parse relay swimmer line like:
    'Rothwell, Vivien E JR Deedy, Anne SR'
    Returns list of (name, year) tuples
    """
    swimmers = []

    # Pattern to match "Name, First [M] YR" repeated
    # This handles two swimmers per line
    pattern = r'([A-Za-z\-]+,\s*[A-Za-z]+(?:\s+[A-Z])?)\s+(FR|SO|JR|SR|GS)?'

    matches = re.findall(pattern, line)
    for name, year in matches:
        name = name.strip()
        year = year if year else None
        if name and ',' in name:  # Must have comma to be a valid name
            swimmers.append((name, year))

    return swimmers


def parse_splits(line: str) -> list:
    """Parse a line of split times - extracts all valid split times from a line"""
    splits = []
    # Find all patterns that look like split times (XX.XX format, typically 20-40 range)
    for part in line.split():
        if re.match(r'^\d+\.\d+$', part):
            try:
                val = float(part)
                # Valid splits are typically between 15 and 120 seconds
                if 15 <= val <= 120:
                    splits.append(val)
            except ValueError:
                continue
    return splits


def is_split_line(line: str) -> bool:
    """Check if line contains split times (may have some garbage text mixed in)"""
    line = line.strip()
    if not line:
        return False

    # Count split-like numbers in the line
    splits = parse_splits(line)

    # If we found at least 2 valid splits, treat it as a split line
    if len(splits) >= 2:
        return True

    # Also check if most parts are split-like
    parts = line.split()
    if len(parts) < 2:
        return False

    time_count = sum(1 for part in parts if re.match(r'^\d+\.\d+$', part))
    return time_count >= len(parts) * 0.5  # Lowered threshold from 0.7 to 0.5


def is_header_line(line: str) -> bool:
    """Check if line is a page header or metadata"""
    skip_patterns = [
        'HY-TEK',
        'MEET MANAGER',
        r'Page\s+\d',
        'Results -',
        'Site License',
        'Aquatic Center',
        r'^\d{4}-\d{4}',
        r'^Team\s+R\s*elay',
        r'^Name\s+Y\s*r',
        'Scores -',
        'Team Rankings',
        'South Carolina',
        'Georgia Institute',
    ]

    for pattern in skip_patterns:
        if re.search(pattern, line):
            return True
    return False


def is_dq_reason_line(line: str) -> bool:
    """Check if line is a DQ reason"""
    # DQ reasons typically describe the violation
    dq_keywords = [
        'Cycle:', 'Stroke:', 'Turn:', 'Start:', 'Finish:',
        'Pull', 'Kick', 'Touch', 'Delay', 'False',
        'Alternating', 'Scissors', 'Flutter', 'Dolphin',
        'Not simultaneous', 'Did not', 'Early', 'Late'
    ]
    line_lower = line.lower()
    return any(kw.lower() in line_lower for kw in dq_keywords)


def is_time_standard_line(line: str) -> bool:
    """Check if line is just a time standard like '1:36.24 A'"""
    return bool(re.match(r'^[\d:\.]+\s*[AB]$', line.strip()))


def is_relay_swimmer_line(line: str) -> bool:
    """Check if line contains relay swimmer names"""
    # Pattern: two names with years like "Rothwell, Vivien E JR Deedy, Anne SR"
    if re.search(r'[A-Za-z]+,\s+[A-Za-z]+.*?(FR|SO|JR|SR)\s+[A-Za-z]+,', line):
        return True
    # Single name with year
    if re.match(r'^[A-Za-z]+,\s+[A-Za-z]+.*?(FR|SO|JR|SR)$', line.strip()):
        return True
    return False


def parse_column_text_with_context(text: str, event_map: dict, last_event: Optional[dict]) -> tuple:
    """Parse column text with event context from other columns"""
    results = []
    current_event = last_event
    current_result = None
    pending_relay_swimmers = []
    relay_leg = 1

    lines = text.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if is_header_line(line):
            continue

        if is_time_standard_line(line):
            continue

        # Check for DQ reason line (must come right after a DQ result)
        if current_result and current_result.is_dq and is_dq_reason_line(line):
            current_result.dq_reason = line
            continue

        # Check for continued event header like "(#8 Men 100 Yard Back)"
        cont_match = re.match(r'\(#(\d+)\s+(Women|Men)', line)
        if cont_match:
            event_num = int(cont_match.group(1))
            if event_num in event_map:
                if current_result:
                    if pending_relay_swimmers:
                        current_result.relay_swimmers = pending_relay_swimmers
                    results.append(current_result)
                    current_result = None
                    pending_relay_swimmers = []
                    relay_leg = 1
                current_event = event_map[event_num]
            continue

        # Check for event header
        event_info = parse_event_header(line)
        if event_info:
            if current_result:
                if pending_relay_swimmers:
                    current_result.relay_swimmers = pending_relay_swimmers
                results.append(current_result)
                current_result = None
                pending_relay_swimmers = []
                relay_leg = 1
            current_event = event_info
            continue

        if not current_event:
            continue

        # Check for split line
        if is_split_line(line):
            if current_result:
                current_result.splits.extend(parse_splits(line))
            continue

        # Check for relay swimmer line
        if current_event['is_relay'] and is_relay_swimmer_line(line) and not re.match(r'^\d+\s+', line):
            swimmers = parse_relay_swimmers(line)
            for name, year in swimmers:
                pending_relay_swimmers.append(RelaySwimmer(name=name, year=year, leg=relay_leg))
                relay_leg += 1
            continue

        # Try to parse as result
        result = None
        if current_event['is_relay']:
            result = parse_relay_result(line, current_event)
            if result:
                # Reset relay swimmer tracking for new relay result
                if current_result:
                    if pending_relay_swimmers:
                        current_result.relay_swimmers = pending_relay_swimmers
                    results.append(current_result)
                pending_relay_swimmers = []
                relay_leg = 1
        elif current_event.get('is_diving', False):
            result = parse_diving_result(line, current_event)
        else:
            result = parse_individual_result(line, current_event)

        if result:
            if current_result and not current_event['is_relay']:
                results.append(current_result)
            elif current_result and current_event['is_relay']:
                # Already handled above
                pass
            current_result = result

    if current_result:
        if pending_relay_swimmers:
            current_result.relay_swimmers = pending_relay_swimmers
        results.append(current_result)

    return results, current_event


def parse_column_text(text: str) -> List[SwimResult]:
    """Parse text from a single column into results (legacy function)"""
    results, _ = parse_column_text_with_context(text, {}, None)
    return results


def extract_meet_info(pdf_path: str) -> dict:
    """
    Extract meet name and date from the PDF header.
    Returns dict with 'meet_name' and 'meet_date' keys.

    Handles formats like:
    - "2025-2026 GT vs SCAR - 1/23/2026"
    - "ACC Championships - 2/15/2025"
    """
    meet_info = {
        'meet_name': None,
        'meet_date': None
    }

    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return meet_info

        # Get first page text
        first_page = pdf.pages[0]
        text = first_page.extract_text()
        if not text:
            return meet_info

        lines = text.split('\n')

        # Look for meet name and date in first 15 lines
        for i, line in enumerate(lines[:15]):
            line = line.strip()
            if not line:
                continue

            # Skip known header patterns
            if any(skip in line for skip in ['HY-TEK', 'MEET MANAGER', 'Site License', 'Page ']):
                continue

            # Look for date pattern (M/D/YYYY or MM/DD/YYYY)
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', line)
            if date_match and not meet_info['meet_date']:
                meet_info['meet_date'] = date_match.group(1)
                # The line with date often has meet name too
                # Remove the date portion and clean up separators
                name_part = re.sub(r'\s*[-–]\s*\d{1,2}/\d{1,2}/\d{4}.*', '', line).strip()
                if not name_part:
                    # Try removing date from anywhere in line
                    name_part = re.sub(r'\d{1,2}/\d{1,2}/\d{4}', '', line).strip()
                    name_part = re.sub(r'\s*[-–]\s*$', '', name_part).strip()  # Remove trailing dash
                if name_part and len(name_part) > 3 and not meet_info['meet_name']:
                    meet_info['meet_name'] = name_part
                continue

            # Also check for date in YYYY-MM-DD format
            date_match2 = re.search(r'(\d{4}-\d{2}-\d{2})', line)
            if date_match2 and not meet_info['meet_date']:
                meet_info['meet_date'] = date_match2.group(1)
                continue

            # If we haven't found a meet name yet, check if this looks like one
            # Meet names are typically longer, don't start with #, and aren't results
            if not meet_info['meet_name']:
                is_meet_name = (
                    len(line) > 10 and
                    not line.startswith('#') and
                    not re.match(r'^\d+\s+', line) and
                    'Results' not in line and
                    ('vs' in line.lower() or '@' in line or 'meet' in line.lower() or
                     'invitational' in line.lower() or 'championship' in line.lower())
                )
                if is_meet_name:
                    meet_info['meet_name'] = line

        # If still no meet name, use the first substantial non-header line
        if not meet_info['meet_name']:
            for line in lines[:10]:
                line = line.strip()
                if (line and len(line) > 15 and
                    not any(skip in line for skip in ['HY-TEK', 'MEET MANAGER', 'Site License', 'Page ', 'Results'])):
                    meet_info['meet_name'] = line
                    break

    return meet_info


def parse_hytek_pdf(pdf_path: str, include_meet_info: bool = False) -> pd.DataFrame:
    """
    Parse HY-TEK Meet Manager PDF results into a DataFrame.

    Args:
        pdf_path: Path to the PDF file
        include_meet_info: If True, also returns meet_info dict as second return value

    Returns:
        DataFrame of results, or tuple of (DataFrame, meet_info) if include_meet_info=True
    """
    all_results = []
    meet_info = extract_meet_info(pdf_path) if include_meet_info else None

    # First pass: extract all event headers
    event_map = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            columns = extract_columns(page)
            for col_text in columns:
                for line in col_text.split('\n'):
                    event_info = parse_event_header(line.strip())
                    if event_info:
                        event_map[event_info['event_number']] = event_info

    # Second pass: parse results with context
    last_event = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            columns = extract_columns(page)
            for col_text in columns:
                results, last_event = parse_column_text_with_context(col_text, event_map, last_event)
                all_results.extend(results)

    if not all_results:
        return pd.DataFrame()

    # Convert to DataFrame
    df = pd.DataFrame([{
        'event_number': r.event_number,
        'event_name': r.event_name,
        'event_gender': r.event_gender,
        'event_distance': r.event_distance,
        'event_stroke': r.event_stroke,
        'is_relay': r.is_relay,
        'is_diving': r.event_stroke == 'Diving',
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
        'dq_reason': r.dq_reason,
        'splits': r.splits,
        'relay_swimmers': [(s.name, s.year, s.leg) for s in r.relay_swimmers] if r.relay_swimmers else [],
    } for r in all_results])

    df = df.sort_values(['event_number', 'place']).reset_index(drop=True)

    if include_meet_info:
        return df, meet_info
    return df


# Convenience functions
def get_individual_results(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df['is_relay']].copy()


def get_relay_results(df: pd.DataFrame) -> pd.DataFrame:
    return df[df['is_relay']].copy()


def get_event_results(df: pd.DataFrame, event_number: int) -> pd.DataFrame:
    return df[df['event_number'] == event_number].copy()


def get_swimmer_results(df: pd.DataFrame, name: str) -> pd.DataFrame:
    return df[df['name'].str.contains(name, case=False, na=False)].copy()


def get_team_results(df: pd.DataFrame, team: str) -> pd.DataFrame:
    return df[df['team'].str.contains(team, case=False, na=False)].copy()


def summarize_meet(df: pd.DataFrame) -> dict:
    return {
        'total_results': len(df),
        'events': df['event_number'].nunique(),
        'teams': df['team'].nunique(),
        'individual_results': len(get_individual_results(df)),
        'relay_results': len(get_relay_results(df)),
        'scored_results': len(df[df['points'].notna()]),
    }


if __name__ == "__main__":
    import sys

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "data/USC @TECH RESULTS.pdf"

    print(f"Parsing: {pdf_path}")
    df = parse_hytek_pdf(pdf_path)

    summary = summarize_meet(df)
    print(f"\n=== Meet Summary ===")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    print("\n=== Events Found ===")
    events = df.groupby(['event_number', 'event_name']).size().reset_index(name='count')
    for _, row in events.iterrows():
        print(f"  #{row['event_number']}: {row['event_name']} ({row['count']} results)")

    print("\n=== Sample Individual Results ===")
    ind_df = get_individual_results(df)
    print(ind_df[['place', 'name', 'year', 'team', 'event_name', 'finals_time', 'points']].head(15).to_string(index=False))

    print("\n=== Sample Relay Results with Swimmers ===")
    relay_df = get_relay_results(df)
    if len(relay_df) > 0:
        for _, row in relay_df.head(3).iterrows():
            print(f"\n  {row['team']} {row['relay_letter']} - {row['event_name']}: {row['finals_time']}")
            if row['relay_swimmers']:
                for name, year, leg in row['relay_swimmers']:
                    print(f"    Leg {leg}: {name} ({year})")

    output_path = pdf_path.replace('.pdf', '_parsed.csv')
    df.to_csv(output_path, index=False)
    print(f"\nResults saved to: {output_path}")
