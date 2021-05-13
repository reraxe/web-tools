# demo-html-editor

```yml
version: "2.1"

services:

  reraxehtmldemo:
    image: reraxe/demo-html-editor:arm64v8
    container_name: reraxehtmldemo
    ports:
      - 8080:80
    restart: unless-stopped
```
