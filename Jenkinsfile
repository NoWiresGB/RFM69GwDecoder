pipeline {

    environment {
        x64Image = ''
        armImage = ''
        dockerCreds = 'dockerhub_id'
    }

    agent any

    stages {

        stage("build") {
            steps {
                echo 'building the containers'
                script {
                    x64Image = docker.build("zmarkella/rfm69gw:devel", "-f Dockerfile .")
                    armImage = docker.build("zmarkella/rfm69gw:devel-armv7hf", "-f Dockerfile.armv7hf .")
                }
            }
        }

        stage("upload") {
            steps {
                echo 'pushing images to registry'
                script {
                    docker.withRegistry( '', dockerCreds ) {
                        x64Image.push()
                        armImage.push()
                    }
                }
            }
        }

    }
}

node {

}