
renderContext = QgsRenderContext()
renderContext.setExtent(layer.extent())
renderer = layer.renderer().clone()
# renderer.setInput(self.mInputSource.dataSource())
renderer.startRender(renderContext, layer.fields())
features = layer.getFeatures(fids)
for i, feature in enumerate(features):
    symbol = renderer.symbolForFeature(feature, renderContext)
    # ...
renderer.stopRender(renderContext)