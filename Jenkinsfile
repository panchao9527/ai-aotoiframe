// 示例前提：Linux agent 已有 Python 3.11、uv 和 Playwright 所需系统库。
// 如公司的节点标签不同，修改下面的 linux。详细准备步骤见 docs/07-ci-troubleshooting.md。
pipeline {
    agent { label 'linux' }

    options {
        timestamps()
        timeout(time: 20, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20', artifactNumToKeepStr: '10'))
    }

    environment {
        TEST_ENV = 'demo'
        UV_PYTHON = '3.11'
        PYTHONUTF8 = '1'
    }

    stages {
        stage('Prepare reports') {
            steps {
                // 只清理当前构建工作区的报告目录，避免上次 JUnit 结果重复计入。
                dir('artifacts') {
                    deleteDir()
                }
            }
        }
        stage('Install') {
            steps {
                // --frozen 确保本地与 CI 使用同一份 uv.lock。
                sh 'uv sync --frozen'
                // 系统库提前放入构建镜像，本步骤只下载匹配版本的浏览器。
                sh 'uv run --frozen python -m playwright install chromium'
            }
        }
        stage('Quality') {
            steps {
                sh 'uv run --frozen ruff check .'
                sh 'uv run --frozen ruff format --check .'
            }
        }
        stage('Test') {
            steps {
                // 不吞退出码；测试失败时 Jenkins 会显示失败。
                sh 'uv run --frozen python -m autotest run --suite all -- --env demo -n 2'
            }
        }
    }

    post {
        always {
            // allowEmptyResults 用于安装阶段就失败、尚未产生报告的情况。
            junit testResults: 'artifacts/**/junit.xml', allowEmptyResults: true
            archiveArtifacts artifacts: 'artifacts/**/*', allowEmptyArchive: true
        }
    }
}
