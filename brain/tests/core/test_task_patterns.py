"""Tasks that repeat: the same kind of task with other months, dates and numbers in it."""

from milo.core.task_patterns import alike, shape


def test_the_shape_leaves_out_numbers_filler_and_words_for_when():
    assert shape("Make the sales report for September 2026, please") == {"sale", "report"}
    assert shape("Put last week's invoices into the Invoices folder") == {"invoice", "folder"}


def test_the_same_task_another_month_is_alike_and_another_task_isnt():
    september = shape("Make the sales report for September")
    assert alike(september, shape("the sales reports for October please"))
    assert not alike(september, shape("Find a flight to Lisbon for October"))
    assert not alike(shape("report"), shape("report"))  # one word is too little to tell
