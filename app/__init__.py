"""Northwind Internal Docs Assistant — the HTTP service (Week 2, Task 3).

The RAG logic (index, graph, memory) lives in exactly one place, the Week 1
capstone (week1/capstone_internal_docs_assistant/app.py). This package is the
service around it; everything else (the Streamlit UI, benchmarks) is a client
of this service over HTTP.
"""
