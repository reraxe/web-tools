# demo-html-editor

Change Image

`
docker run -d -p 8080:8000 -name=reraxehtmldemo --restart=always reraxe/demo-html-editor:arm64v8
`


```yml
version: "2.1"

services:

  reraxehtmldemo:
    image: reraxe/demo-html-editor:arm64v8
    container_name: reraxehtmldemo
    ports:
      - 8080:80
    restart: always
```
