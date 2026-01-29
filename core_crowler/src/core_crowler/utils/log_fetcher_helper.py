
import re
from datetime import datetime, timedelta

def clean_ansi_codes(data: bytes) -> bytes:
    """
    Removes ANSI escape codes from the given data bytes.

    ANSI escape codes are often used to add color or formatting to terminal output.
    This function strips such codes, returning a plain text version.

    Args:
        data (bytes): The input data potentially containing ANSI escape codes.

    Returns:
        bytes: The input data with all ANSI escape codes removed.
    """
    ansi_escape = re.compile(rb'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub(b'', data)

def parse_timestamp(line: str) -> datetime:
    """
    Extracts and parses a timestamp from a log line.

    The function searches for a timestamp in the format 'MM/DD HH:MM:SS.mmm:' within the given line,
    prepends the current year, and returns a datetime object representing the parsed timestamp.
    If no timestamp is found, returns None.

    Args:
        line (str): The log line containing the timestamp.

    Returns:
        datetime or None: The parsed datetime object if a timestamp is found, otherwise None.
    """
    match = re.search(r'(\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d{3}):', line)
    if match is None:
        return None
    ts_str = match.group(1)
    full_ts_str = f"{datetime.now().year}/{ts_str}"
    return datetime.strptime(full_ts_str, "%Y/%m/%d %H:%M:%S.%f")