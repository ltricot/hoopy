# test our proxy through curl
#
# compare requests through the proxy and through
# no proxy. test both http and https (although it
# shouldn't matter)


# launch our proxy server
hoopy --ip localhost --port 8080 > /dev/null &

# test both http and https
domains=('http://neverssl.com', 'http://httpbin.org', 'https://www.google.com/')
failed=()

code=0
for domain in domains; do
    # request without and with proxy
    yes_proxy=$(curl -x socks4://localhost:8080 $domain 2>/dev/null)
    no_proxy=$(curl $domain 2>/dev/null)

    # check whether we obtained the right html page
    if [[ $yes_proxy != $no_proxy ]]; then
        failed+=($domain)
        code=1
    fi
done

if [[ $code ]]; then
    echo "success"
else
    echo "failure" $failed
fi

kill %1
exit $code

