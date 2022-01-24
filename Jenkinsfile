pipeline {

    environment {
        x64Image = ''
        armImage = ''
        dockerCreds = 'dockerhub_id'
        imageTag = ''
    }

    agent any

    stages {

        stage("build") {
            steps {
                echo 'building the containers'
                script {
                    if (env.TAG_NAME.equals('devel')) {
                        imageTag = 'devel'
                    } else {
                        imageTag = 'latest'
                    }
                    x64Image = docker.build('zmarkella/rfm69gw-decoder:' + imageTag, '-f Dockerfile .')
                    armImage = docker.build('zmarkella/rfm69gw-decoder:' + imageTag + '-armv7hf', '-f Dockerfile.armv7hf .')
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