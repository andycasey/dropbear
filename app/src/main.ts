import { request } from "https";
// const url: string = "https://api.adsabs.harvard.edu/v1/search/query/";

export class ADSRequest {

  search(query: string, token: string) {
    const options = {
      hostname: "google.com",
      port: 443,
      path: "/",
      method: "GET",
      headers: {
        "User-Agent": "ads-api-client/javascript",
        "Content-Type": "application/json"
      }
    };
    request(options, (response: any) => {
      console.log(response);
    });

  }

}

(new ADSRequest()).search("face", "what");