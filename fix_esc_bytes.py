with open("tests/test_membership_core.py", "rb") as f:
    content = f.read()

# The correct full line with HTML entity <script>
html_entity = bytes([0x26, 0x6c, 0x74, 0x3b, 0x73, 0x63, 0x72, 0x69, 0x70, 0x74, 0x26, 0x67, 0x74, 0x3b])
line = b'    assert escape_html("<script>") == "' + html_entity + b'"'

old = b'    assert escape_html("<script>") == "<script>"'
print("old:", repr(old))
print("new:", repr(line))

content = content.replace(old, line)
with open("tests/test_membership_core.py", "wb") as f:
    f.write(content)

print("done")
with open("tests/test_membership_core.py", "rb") as f:
    content = f.read()
idx = content.find(b"def test_escape_html")
print(repr(content[idx:idx+200]))