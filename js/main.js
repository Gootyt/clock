'use strict';

const clockContentHandler = () => {
    document
        .querySelector('.clock')
        .textContent = new Date().toLocaleTimeString('hu');
}

setInterval(clockContentHandler, 1000);