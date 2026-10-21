"""Legacy launch/import adapter. Application ownership is in FUE Core."""
if __name__ == "__main__":
    from fue_core.server import run
    run()
else:
    from fue_core.app import app
