from app.chatbot.policy import is_write_request


def test_delete_request_is_blocked():
    assert is_write_request(
        "Delete invoice number 15"
    ) is True


def test_update_request_is_blocked():
    assert is_write_request(
        "Update this payable to 50000"
    ) is True


def test_create_request_is_blocked():
    assert is_write_request(
        "Create a new voucher"
    ) is True


def test_modify_request_is_blocked():
    assert is_write_request(
        "Modify the ledger amount"
    ) is True


def test_read_payable_request_is_allowed():
    assert is_write_request(
        "What are my payables?"
    ) is False


def test_read_receivable_request_is_allowed():
    assert is_write_request(
        "How much money do customers owe us?"
    ) is False


def test_highest_payable_request_is_allowed():
    assert is_write_request(
        "Which party has the highest payable?"
    ) is False