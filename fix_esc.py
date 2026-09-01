# Write the actual HTML entity bytes directly
with open("tests/test_membership_core.py", "rb") as f:
    content = f.read()
# Replace the literal <script> with the HTML entity <script>
# The literal angle brackets are b"<script>" - replace with HTML entity
old = b'escape_html("<script>") == "<script>"'
new = b'escape_html("<script>") == "<script>"'
content = content.replace(old, new)
with open("tests/test_membership_core.py", "wb") as f:
    f.write(content)
print("done")
# Verify
with open("tests/test_membership_core.py", "rb") as f:
    lines = f.readlines()
print(repr(lines[120]))