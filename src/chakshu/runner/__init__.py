"""The half of Chakshu that runs inside GitHub Actions (`chakshu action`).

It imports nothing that needs the database: it gets everything from the server
over HTTP and runs the review agent on the runner.
"""
