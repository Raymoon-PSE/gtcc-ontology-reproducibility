"""Frozen baseline: canonical stream interface, before external schema changes."""

def adapt(record, configuration_text):
    return dict(record)
