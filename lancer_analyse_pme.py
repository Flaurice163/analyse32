import webview


URL_APPLICATION = "https://analyse-pme.streamlit.app/"


def main():
    webview.create_window(
        "Analyse PME",
        URL_APPLICATION,
        width=1280,
        height=850,
        min_size=(760, 560),
    )
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
