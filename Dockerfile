FROM ubuntu:18.04

RUN apt-get -y update
RUN apt-get -y install \
    wget \
    python3 \
    python3-pip \
    libssl-dev \
    curl \
    git

# install nodejs truffle web3 ganache-cli
RUN curl -sL https://deb.nodesource.com/setup_12.x | bash -
RUN apt-get -y install nodejs
RUN npm -g config set user root
RUN npm install -g truffle web3 ganache-cli

# install solc
# RUN wget https://github.com/ethereum/solidity/releases/download/v0.4.25/solc-static-linux
# RUN mv solc-static-linux /usr/bin/solc
# RUN chmod +x /usr/bin/solc
RUN pip3 install solc-select
RUN solc-select install 0.4.26
RUN solc-select install 0.5.16
RUN solc-select install 0.6.11
RUN solc-select use 0.4.26


# install go
RUN wget https://dl.google.com/go/go1.10.8.linux-amd64.tar.gz
RUN tar -xvf go1.10.8.linux-amd64.tar.gz
RUN mv go /usr/lib/go-1.10
RUN mkdir /go
ENV GOPATH=/go
ENV GOROOT=/usr/lib/go-1.10
ENV PATH=$PATH:$GOPATH/bin
ENV PATH=$PATH:$GOROOT/bin

# install z3
RUN git clone https://github.com/Z3Prover/z3.git
WORKDIR /z3
RUN git checkout z3-4.8.6
RUN python3 scripts/mk_make.py --python
WORKDIR /z3/build
RUN make -j7
RUN make install

# python deps take a long time so do them first
WORKDIR /go/src/ilf
COPY ./requirements.txt .
RUN pip3 install -r requirements.txt --no-cache-dir

# copy ilf
ADD ./ /go/src/ilf/

# install go-ethereum
RUN mkdir -p /go/src/github.com/ethereum/
WORKDIR /go/src/github.com/ethereum/
RUN git clone https://github.com/ethereum/go-ethereum.git
WORKDIR /go/src/github.com/ethereum/go-ethereum
RUN git checkout 86be91b3e2dff5df28ee53c59df1ecfe9f97e007
RUN git apply /go/src/ilf/script/patch.geth
# RUN go get github.com/ethereum/go-ethereum
# WORKDIR /go/src/github.com/ethereum/go-ethereum
# RUN git checkout 86be91b3e2dff5df28ee53c59df1ecfe9f97e007
# RUN git apply /go/src/ilf/script/patch.geth

WORKDIR /go/src/ilf
RUN go build -o execution.so -buildmode=c-shared export/execution.go

ENTRYPOINT [ "python3", "toolize/entry.py" ]
