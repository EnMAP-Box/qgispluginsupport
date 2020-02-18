import qps.testing
import qps.resources

from qps import QPS_RESOURCE_FILE

resource_files = qps.resources.findQGISResourceFiles()
resource_files.append(QPS_RESOURCE_FILE)
# or qps.initResources()

app = qps.testing.start_app(resources=resource_files)
from qps.resources import ResourceBrowser

browser = ResourceBrowser()
browser.show()

app.exec_()