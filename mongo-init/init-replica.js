// mongo-init/init-replica.js
function main() {
  try {
    rs.initiate({ _id: 'rs0', members: [{ _id: 0, host: 'mongo:27017' }] });
    print('Replica set rs0 initiated');
  } catch (e) {
    var msg = e && e.message ? e.message : '';
    var alreadyDone = (e && e.codeName === 'AlreadyInitialized') ||
                       /already initialized/i.test(msg);

    if (alreadyDone) {
      print('Replica set rs0 already initialised - skipping');
    } else {
      print('Error initiating replica set: ' + msg);
      throw e;
    }
  }
}

main();