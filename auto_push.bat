@echo off
cd /d E:\MARVIS_Skill_V2
echo === MARVIS V2.0 基线自动同步 ===
echo.
git add .
git commit -m "auto sync: config / doc update"
git push origin v2.0_release
git push --tags
echo.
echo === 云端同步完成 ===
pause
