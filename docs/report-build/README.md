# Rebuild the academic report

The report uses the supplied SkillSim DOCX as a formatting reference. Its body and identities are replaced with the AWS project content; the original file is never overwritten. The confirmed student details are in `build-report.py`. Technical content is editable in `report-content.py`; `report-content.json` is its generated intermediate source.

The builder reads the actual current release from `reports/live-deployment.json`. Refresh evidence before rebuilding. Use the Codex bundled document Python runtime on this machine, which already has python-docx, Pillow, pypdf and pypdfium2:

```powershell
Set-Location D:\aws
$reportPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $reportPython docs/report-build/report-content.py
& $reportPython docs/report-build/draw-diagrams.py
& $reportPython docs/report-build/build-report.py --reference "$env:USERPROFILE\Downloads\SkillSim_Secure_Software_Engineering_Capstone_Report_Final.docx"
```

The output is `deliverables/AWS_DevSecOps_Capstone_Report_Final.docx`. Open it in Word, update the table of contents, list of figures and page fields, save, render and inspect every page. The published final copy has already undergone that process. Preserve readable screenshots and captions, check the author's exact details and keep historical screenshots distinct from the newest release evidence.

Generated engineering diagrams represent design models. The supplied screenshots represent actual observations. Avoid fabricating a screenshot or interpreting a logical model as proof of live behavior.
