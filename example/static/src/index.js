import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
// stupid hack so that leaflet's images work after going through webpack
import marker from 'leaflet/dist/images/marker-icon.png';
import marker2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
    iconRetinaUrl: marker2x,
    iconUrl: marker,
    shadowUrl: markerShadow
});

import './styles.css';
import {runWebGLDemo} from './webgl-demo';

function setStatus(element, success, message) {
    if (success === null) {
        element.className = 'badge badge-secondary';
    } else if (success === true) {
        element.className = 'badge badge-success';
    } else {
        element.className = 'badge badge-danger';
    }
    element.textContent = message;

}

function initAudio() {
    let status = document.querySelector('#webcam-status');
    let webcamButton = document.querySelector('#webcam-button');

    webcamButton.onclick = () => {
        let video = document.getElementById('video');
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({video: true})
                .then(function(stream) {
                    video.srcObject = stream;
                    setStatus(status, true, 'OK');
                })
                .catch(function(error) {
                    setStatus(status, false, error);
                });
        } else {
            setStatus(status, false, 'insecure host');
        }
    }
}

function initGeolocation() {
    let map = L.map('map').setView([51.505, -0.09], 13);

    L.tileLayer('https://api.mapbox.com/styles/v1/{id}/tiles/{z}/{x}/{y}?access_token=pk.eyJ1IjoibWFwYm94IiwiYSI6ImNpejY4NXVycTA2emYycXBndHRqcmZ3N3gifQ.rJcFIG214AriISLbB6B5aw', {
        maxZoom: 18,
        attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors, ' +
            '<a href="https://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>, ' +
            'Imagery © <a href="https://www.mapbox.com/">Mapbox</a>',
        id: 'mapbox/streets-v11',
        tileSize: 512,
        zoomOffset: -1
    }).addTo(map);


    let status = document.querySelector('#geolocation-status');
    let geoButton = document.querySelector('#geolocation');
    geoButton.onclick = () => {
        if (navigator.geolocation) {
            setStatus(status, null, 'querying, please wait...');
            geoButton.disabled = true;

            navigator.geolocation.getCurrentPosition(
                (position) => {
                    geoButton.disabled = false;
                    let pos = [position.coords.latitude, position.coords.longitude];
                    L.marker(pos).addTo(map);
                    map.setView(pos);
                    setStatus(status, true, 'OK');
                },
                (error) => {
                    geoButton.disabled = false;
                    setStatus(status, false, error.message);
                },
            );
        } else {
            setStatus(status, false, 'not supported by this browser');
        }
    };
}

function initNotifications() {
    let button = document.querySelector('#notifications');
    let status = document.querySelector('#notifications-status');

    function checkNotificationPromise() {
        try {
            Notification.requestPermission().then();
            return true;
        } catch (e) {
            return false;
        }
    }

    function handlePermission(permission) {
        if (permission === 'denied') {
            setStatus(status, false, 'permission denied');
        } else if (permission === 'default') {
            setStatus(status, false, 'no action (denied)');
        } else if (permission === 'granted') {
            new Notification('Test', {'body': 'body'});
            setStatus(status, true, 'OK');
        } else {
            throw permission;
        }
    }

    button.onclick = () => {
        if (!('Notification' in window)) {
            setStatus(status, false, 'This browser does not support notifications');
        } else {
            if (checkNotificationPromise()) {
                Notification.requestPermission()
                    .then((permission) => {
                        handlePermission(permission);
                    })
            } else {
                Notification.requestPermission(function(permission) {
                    handlePermission(permission);
                });
            }
        }
    }
}

function initWebGL() {
    const canvas = document.querySelector('#webgl');
    let status = document.querySelector('#webgl-status');
    let [success, message] = runWebGLDemo(canvas);

    if (success) {
        setStatus(status, true, 'OK');
    } else {
        setStatus(status, false, message);
    }
}

window.onConnect = (server) => {
    document.querySelector('title').text = `Demo app on ${location}`;

    initAudio();
    initGeolocation();
    initNotifications();
    initWebGL();
    console.log('connected server ', server);
    window.resizeTo(
        document.body.offsetWidth,
        document.body.offsetHeight + 50
    );
};
