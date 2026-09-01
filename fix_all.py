with open("tests/test_membership_core.py", "rb") as f:
    content = f.read()

# Write the entire correct function
html_entity = bytes([0x26, 0x6c, 0x74, 0x3b, 0x73, 0x63, 0x72, 0x69, 0x70, 0x74, 0x26, 0x67, 0x74, 0x3b])

old_func = b'def test_escape_html():\n    assert escape_html("<script>") == <script>"\n    assert escape_html("hello") == "hello"\n    assert escape_html("") == ""\n\n\n'
new_func = b'def test_escape_html():\n    assert escape_html("<script>") == "' + html_entity + b'"\n    assert escape_html("hello") == "hello"\n    assert escape_html("") == ""\n\n\n'

print("old:", repr(old_func[:80]))
print("new:", repr(new_func[:80]))

content = content.replace(old_func, new_func)
with open("tests/test_membership_core.py", "wb") as f:
    f.write(content)

print("done")
with open("tests/test_membership_core.py", "rb") as f:
    content = f.read()
idx = content.find(b"def test_escape_html")
print(repr(content[idx:idx+200]))