def tests = [:]

tests['rspec'] = {
  node('docker') {
    checkout scm

    // rspec-bash needs ruby + netcat
    docker.image('lsstsqre/rspec-bash-env:latest').inside("-e HOME=${pwd()}") {
      sh 'bundle install --path .bundle'
      sh 'bundle exec rubocop'
      sh 'bundle exec rspec --format doc'
    } // .inside
  } // node
}

tests['shellcheck'] = {
  node('docker') {
    deleteDir()

    dir('lsstsw') {
      git([
        url: 'https://github.com/lsst/lsstsw',
        branch: 'main',
      ])
    }

    dir('ci-scripts') {
      checkout scm
    }

    docker.image('koalaman/shellcheck-alpine:v0.4.6').inside("--entrypoint='' -e HOME=${pwd()}") {
      // sadly, dir() doesn't work inside of containers...
      // we can't dir before .inside() either as we want the workspace root to
      // be mounted inside the container so ./lsstsw is accessible
      sh 'cd ci-scripts; shellcheck -x *.sh'
    } // .inside
  } // node
}

stage('tests') {
  parallel tests
}
