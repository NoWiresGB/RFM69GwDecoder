pipeline {

    agent any

    stages {

        stage("build") {

            steps {
                echo 'building the containers'
                x64Image = docker.build("zmarkella/rfm69gw:devel", "-f Dockerfile .")
            }
        }

        stage("upload") {

            steps {
                echo 'pushing images to registry'
            }
        }
    }
}

node {

}