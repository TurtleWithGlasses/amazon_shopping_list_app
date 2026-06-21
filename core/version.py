"""Single source of truth for the app version.

Keep this in sync with version_info.txt (embedded in the exe) and
installer/PriceTracker.iss (AppVersion) when cutting a release.
"""
__version__ = "0.3.0"

# owner/repo on GitHub, used by the updater to query the latest release.
GITHUB_REPO = "TurtleWithGlasses/amazon_shopping_list_app"
