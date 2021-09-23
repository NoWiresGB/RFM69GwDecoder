pipeline {

    agent any

    stages {

        stage("build") {

            steps {
                echo 'building the containers'
                docker build -t zmarkella/rfm69gw:devel -f Dockerfile .
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