'''
pip requests pyside6 aiohttp bs4 lxml playwright -i https://pypi.tuna.tsinghua.edu.cn/simple

pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple

```posershell

pyinstaller app_book.py `
--paths=. `
--hidden-import=book_util `
--hidden-import=shelf `
--hidden-import=component `
--hidden-import=text_to_epub `
--hidden-import=button_component

```

还在开发阶段，功能有许多缺陷。主要功能有导出pdf、md、epub 和查询、收藏、下载。

百度网盘链接：
- 链接: https://pan.baidu.com/s/19bzPfJfaz6EZcgGBrYeUDQ?pwd=r7c3 提取码: r7c3

''' 
