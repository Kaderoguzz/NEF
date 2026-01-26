
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
    return ansi_escape.sub('', data)

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
    #return datetime.strptime(ts_str, "%y/%m/%d %H:%M:%S.%f")

def load_logs(input_logs: list[str]) -> list[tuple[datetime, str]]:
    """
    Processes a list of log lines, cleaning ANSI codes, parsing timestamps, and grouping related log entries.

    Args:
        input_logs (list[str]): List of raw log lines as strings.

    Returns:
        list[tuple]: A list of tuples, each containing a parsed timestamp and the corresponding cleaned log line.
        If a line contains "ueLocation" and follows a timestamped log, it is appended to the previous log entry.
    """
    logs = []
    for line in input_logs:
        line = clean_ansi_codes(line.strip())
        if not line or line == '-':
            continue
        ts = parse_timestamp(line)
        if ts:
            logs.append((ts, line))
        elif "ueLocation" in line and logs:
            logs[-1] = (logs[-1][0], f"{logs[-1][1]} {line}")
        else:
            continue
    return logs