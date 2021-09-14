import typing
import re

text = r'enmap@"band 49 (0.685000 Micrometers)" "xyz"'

rx = re.compile(r'(?P<varname>[^ ]+)@"(?P<bandname>[^"]+)"')
match = rx.match(text)
assert isinstance(match, typing.Match)
print(f"varname={match.group('varname')}")
print(f"bandname={match.group('bandname')}")