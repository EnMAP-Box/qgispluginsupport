set QT_QPA_PLATFORM=offscreen
set CI=True
rmdir /s /q test-outputs
rmdir /s /q test-reports
pytest --no-cov-on-fail --cov-config=.coveragec
coverage-badge -o coverage.svg  -f -v %*