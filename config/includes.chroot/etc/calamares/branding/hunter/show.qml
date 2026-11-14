/* SMD Linux 1.0 - installer slideshow (Calamares slideshow API 2) */
import QtQuick 2.0
import calamares.slideshow 1.0

Presentation {
    id: presentation

    Timer {
        interval: 7000
        running: true
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#1d232b"
        }
        Image {
            anchors.centerIn: parent
            source: "slide-1.png"
            width: parent.width * 0.92
            fillMode: Image.PreserveAspectFit
        }
    }

    Slide {
        Rectangle {
            anchors.fill: parent
            color: "#1d232b"
        }
        Image {
            anchors.centerIn: parent
            source: "slide-2.png"
            width: parent.width * 0.92
            fillMode: Image.PreserveAspectFit
        }
    }
}
