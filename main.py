import warnings
from urllib3.exceptions import DependencyWarning
warnings.filterwarnings("ignore", category=DependencyWarning)
try:
    from requests.exceptions import RequestsDependencyWarning
    warnings.filterwarnings("ignore", category=RequestsDependencyWarning)
except ImportError:
    pass

from app import WoWTranslatorApp


if __name__ == "__main__":
    app = WoWTranslatorApp()
    app.root.mainloop()
