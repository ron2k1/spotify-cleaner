"""Pluggable listen-scoring strategies (Strategy pattern).

Each scorer turns a different data source into a uniform
``{track_id: PlayStats}`` mapping so the planner never has to care where the
listen data came from. Swapping sources is a one-line change in the CLI.
"""
