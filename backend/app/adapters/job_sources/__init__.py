"""One module per job provider.

Each turns that provider's JSON into `RawPosting` and does nothing else. Substitution for
tests and demo mode happens at the HTTP transport instead, so this normalisation always runs
for real — the lesson from ticket 06, where a fixture parser returning a finished result
meant demo mode exercised different code from production.
"""
