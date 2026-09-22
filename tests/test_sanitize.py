from sharenet.sanitize import sanitize_text


def test_sanitizes_password_ip_and_mac():
    source = "password=hello 203.0.113.15 aa:bb:cc:dd:ee:ff"
    result = sanitize_text(source)
    assert "hello" not in result
    assert "203.0.113.15" not in result
    assert "aa:bb:cc:dd:ee:ff" not in result
    assert "[REDACTED]" in result


def test_keeps_non_sensitive_message():
    assert sanitize_text("router connection failed") == "router connection failed"
