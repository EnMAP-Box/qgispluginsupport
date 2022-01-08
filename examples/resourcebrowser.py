import qps.testing
import qps.resources

from qps import QPS_RESOURCE_FILE
from qps.resources import ResourceBrowser

resource_files = qps.resources.findQGISResourceFiles()
resource_files.append(QPS_RESOURCE_FILE)
app = qps.testing.start_app(resources=resource_files)

browser = ResourceBrowser()
browser.show()

app.exec_()
